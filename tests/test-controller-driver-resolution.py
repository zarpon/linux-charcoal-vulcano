#!/usr/bin/env python3
"""Exercise release selection, failure policy and PKGBUILD source pinning."""
import importlib.util
from pathlib import Path
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("drivers", ROOT / "automation/resolve-controller-drivers.py")
drivers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drivers)
SHA = "a" * 40


def release(tag="v1.2.3", **overrides):
    return dict(tag_name=tag, draft=False, prerelease=False,
                html_url="https://github.com/upstream/releases/tag/" + tag,
                published_at="2026-10-02T00:00:00Z", **overrides)


class DriverResolutionTests(unittest.TestCase):
    def test_latest_release_resolves_exact_tag_commit(self):
        calls = []
        def request(path):
            calls.append(path)
            return release() if path.endswith("releases/latest") else {"sha": SHA}
        record = drivers.resolve_driver("xpadneo", request)
        self.assertEqual(record["mode"], "latest-release")
        self.assertEqual(record["commit"], SHA)
        self.assertEqual(calls[-1], "repos/atar-axis/xpadneo/commits/v1.2.3")

    def test_xpad_noone_prefers_release_when_available(self):
        record = drivers.resolve_driver("xpad-noone", lambda p: release() if p.endswith("latest") else {"sha": SHA})
        self.assertEqual(record["mode"], "latest-release")

    def test_only_noone_can_use_default_branch_without_releases(self):
        def request(path):
            if path.endswith("latest"):
                raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
            if "releases?" in path:
                return []
            if path.endswith("xpad-noone"):
                return {"default_branch": "main"}
            self.assertTrue(path.endswith("commits/main"))
            return {"sha": SHA}
        record = drivers.resolve_driver("xpad-noone", request)
        self.assertEqual(record["ref"], "main")
        self.assertEqual(record["mode"], "default-branch-head-no-stable-release")
        for name in ("xpadneo", "xone"):
            with self.assertRaises(urllib.error.HTTPError):
                drivers.resolve_driver(name, request)

    def test_api_errors_do_not_fall_back_to_stale_sources(self):
        for code in (403, 429, 500):
            def request(path):
                raise urllib.error.HTTPError(path, code, "Unavailable", {}, None)
            with self.assertRaises(urllib.error.HTTPError):
                drivers.resolve_driver("xpad-noone", request)

    def test_prerelease_and_draft_are_rejected(self):
        for flag in ("prerelease", "draft"):
            record = release(); record[flag] = True
            with self.assertRaises(drivers.ResolutionError):
                drivers.resolve_driver("xone", lambda p: record)

    def test_invalid_commit_is_rejected(self):
        with self.assertRaises(drivers.ResolutionError):
            drivers.resolve_driver("xone", lambda p: release() if p.endswith("latest") else {"sha": "master"})

    def test_pkgbuild_updates_all_sources_and_xpadneo_version(self):
        text = (ROOT / "PKGBUILD").read_text()
        records = {name: dict(repository=repo, ref="v9.8.7", commit=SHA)
                   for name, repo in drivers.REPOSITORIES.items()}
        result = drivers.update_pkgbuild(text, records)
        self.assertIn("_xpadneo_version=9.8.7", result)
        for repo in drivers.REPOSITORIES.values():
            self.assertIn(f"{repo}.git#commit={SHA}", result)
        self.assertEqual(drivers.update_pkgbuild(result, records), result)
        self.assertIn("VERSION=$_xpadneo_version modules", result)
        self.assertEqual(text[text.index("sha256sums=("):text.index("export KBUILD_BUILD_HOST")],
                         result[result.index("sha256sums=("):result.index("export KBUILD_BUILD_HOST")])

    def test_missing_source_fails_before_write(self):
        records = {name: dict(repository=repo, ref="v9.8.7", commit=SHA)
                   for name, repo in drivers.REPOSITORIES.items()}
        with self.assertRaises(drivers.ResolutionError):
            drivers.update_pkgbuild("_xpadneo_version=1.0\n", records)


if __name__ == "__main__":
    unittest.main()
