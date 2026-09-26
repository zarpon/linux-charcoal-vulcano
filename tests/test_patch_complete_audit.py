import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "complete_upstream_audit", ROOT / "automation/audit-latest-patch-versions.py"
)
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class CompleteAuditTests(unittest.TestCase):
    def run_audit(self, mutation=None):
        specs = {
            "adios": {"name": "adios", "kind": "github_tree", "project_version_regex": ".+"},
            "auxiliary_native": {"name": "auxiliary_native", "kind": "github_tree"},
        }
        records = {
            name: {
                "content_bytes": b"current bytes\n",
                "commit": "a" * 40, "path": name + ".patch", "url": "https://example.invalid/" + name,
                "sha256": hashlib.sha256(b"current bytes\n").hexdigest(),
                "project_version": "3.3.0r2", "origin": "upstream-compatible",
            } for name in specs
        }
        lock_records = {name: {k: v for k, v in record.items() if k != "content_bytes"}
                        for name, record in records.items()}
        if mutation:
            mutation(lock_records)
        lock = {"kernel": {"version": "6.16.12"}, "components": lock_records, "auxiliary_components": {}}
        candidate = audit.resolver.Candidate("r2.patch", "a" * 40, "https://example.invalid",
                                             0, (7, 3), "3.3.0r2")
        with (
            mock.patch.object(audit, "load_policy", return_value=({}, specs)),
            mock.patch.object(audit, "TRACKED_LOCAL_BYTES", set()),
            mock.patch.object(Path, "read_text", return_value=json.dumps(lock)),
            mock.patch.object(audit.resolver, "upstream_candidates", return_value=[candidate]),
            mock.patch.object(audit.resolver, "resolve_component",
                              side_effect=lambda source, *args: records[source["name"]]) as resolve,
        ):
            result = audit.main()
        return result, resolve.call_count

    def test_every_family_is_audited_even_unversioned_auxiliary(self):
        result, calls = self.run_audit()
        self.assertEqual(result, 0)
        self.assertEqual(calls, 2)

    def test_same_version_payload_drift_is_rejected(self):
        result, _ = self.run_audit(lambda rows: rows["adios"].update(sha256="f" * 64))
        self.assertEqual(result, 2)

    def test_auxiliary_upstream_head_drift_is_rejected(self):
        result, _ = self.run_audit(lambda rows: rows["auxiliary_native"].update(commit="b" * 40))
        self.assertEqual(result, 2)

    def test_older_project_release_is_rejected(self):
        result, _ = self.run_audit(lambda rows: rows["adios"].update(project_version="3.3.0"))
        self.assertEqual(result, 2)

    def test_all_project_filters_include_rc_and_revision(self):
        _, specs = audit.load_policy()
        paths = {
            "lru_marie": "patches/testing/0001-linux7.3-rc1-lru_marie-0.12.0-rc2.patch",
            "adios": "patches/stable/0001-linux7.3-rc1-ADIOS-3.4.0r2.patch",
            "bore": "patches/testing/0001-linux7.3-rc1-bore-7.1.0-rc2.patch",
            "poc_selector": "patches/testing/0001-7.3-rc1-poc-selector-v3.1.0-rc2.patch",
            "nap": "patches/testing/0001-7.3-rc1-nap-v0.6.0-rc2.patch",
            "zram_ir": "patches/testing/0001-linux7.3-rc1-zram-ir-1.4-rc2.patch",
        }
        for name, path in paths.items():
            with self.subTest(name=name):
                self.assertIsNotNone(re.fullmatch(specs[name]["filename_regex"], path))
                self.assertIsNotNone(audit.resolver.candidate_project_version(specs[name], path))
        self.assertGreater(audit.resolver.project_version_key("3.4.0-rc1"),
                           audit.resolver.project_version_key("3.3.0r9"))
        self.assertGreater(audit.resolver.project_version_key("3.3.0r2"),
                           audit.resolver.project_version_key("3.3.0"))


if __name__ == "__main__":
    unittest.main()
