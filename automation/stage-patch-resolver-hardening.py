#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

resolver = Path("automation/resolve-latest-patches.py")
text = resolver.read_text(encoding="utf-8")
needle = '''    expected = spec.get("local_port_upstream_sha256")
    if expected and official_sha != expected:
        raise ResolveError(
            f"local port for {spec['name']} follows upstream SHA-256 {expected}, "
            f"but current upstream is {official_sha}; refresh and validate the port"
        )
    upstream |= {"sha256": official_sha, "size": len(official)}
'''
replacement = '''    expected = spec.get("local_port_upstream_sha256")
    if expected and official_sha != expected:
        raise ResolveError(
            f"local port for {spec['name']} follows upstream SHA-256 {expected}, "
            f"but current upstream is {official_sha}; refresh and validate the port"
        )

    expected_project_version = spec.get("local_port_project_version")
    if candidate.project_version:
        if expected_project_version is None:
            raise ResolveError(
                f"local port for {spec['name']} must declare "
                "local_port_project_version to track the selected upstream release"
            )
        if str(expected_project_version) != candidate.project_version:
            raise ResolveError(
                f"local port for {spec['name']} implements project version "
                f"{expected_project_version}, but the selected closest upstream "
                f"source is {candidate.project_version}; refresh and validate the port"
            )
    elif not expected:
        raise ResolveError(
            f"unversioned local port for {spec['name']} must declare "
            "local_port_upstream_sha256"
        )

    upstream |= {"sha256": official_sha, "size": len(official)}
'''
if text.count(needle) != 1:
    raise SystemExit(f"local-port guard anchor count: {text.count(needle)}")
resolver.write_text(text.replace(needle, replacement, 1), encoding="utf-8")

Path("tests/test-resolve-latest-patches.py").write_text(
    '''#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "automation/resolve-latest-patches.py"
SPEC = importlib.util.spec_from_file_location("charcoal_patch_resolver", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

PATCH = b"From 1111111111111111111111111111111111111111 Mon Sep 17 00:00:00 2001\\nSubject: [PATCH] demo\\n\\ndiff --git a/demo.c b/demo.c\\n--- a/demo.c\\n+++ b/demo.c\\n@@ -1 +1 @@\\n-old\\n+new\\n"


class LocalPortTrackingTests(unittest.TestCase):
    def candidate(self, version: str | None) -> object:
        return MODULE.Candidate(
            path="patches/stable/0001-linux6.16-demo-2.0.patch",
            sha="a" * 40,
            url="https://example.invalid/demo.patch",
            compatibility=2,
            kernel_version=(6, 16, 0),
            project_version=version,
        )

    @staticmethod
    def base_spec() -> dict[str, object]:
        return {
            "name": "demo",
            "repository": "example/demo",
            "local_port": "demo.patch",
            "port_for_kernel": "6.16.12",
            "port_when_incompatible": True,
            "local_port_project_version": "1.0",
        }

    def test_version_change_rejects_stale_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate("2.0")]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                with self.assertRaisesRegex(MODULE.ResolveError, "selected closest upstream source is 2.0"):
                    MODULE.resolve_github_component(self.base_spec(), "6.16.12", None, root)

    def test_matching_version_accepts_tracked_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            spec = self.base_spec()
            spec["local_port_project_version"] = "2.0"
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate("2.0")]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                selected = MODULE.resolve_github_component(spec, "6.16.12", None, root)
            self.assertEqual(selected["origin"], "local-port")
            self.assertEqual(selected["upstream"]["project_version"], "2.0")

    def test_unversioned_port_requires_upstream_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            spec = self.base_spec()
            spec.pop("local_port_project_version")
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate(None)]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                with self.assertRaisesRegex(MODULE.ResolveError, "must declare local_port_upstream_sha256"):
                    MODULE.resolve_github_component(spec, "6.16.12", None, root)


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

workflow = Path(".github/workflows/push.yml")
text = workflow.read_text(encoding="utf-8")
compile_line = "          python3 -m py_compile automation/resolve-latest-patches.py automation/validate-patch-lock.py automation/finalize-pkgbuild-checksums.py\n"
test_line = "          python3 tests/test-resolve-latest-patches.py\n"
if test_line not in text:
    if text.count(compile_line) != 1:
        raise SystemExit("normal workflow compile anchor is missing")
    text = text.replace(compile_line, compile_line + test_line, 1)
    workflow.write_text(text, encoding="utf-8")
