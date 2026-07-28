#!/usr/bin/env python3
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

PATCH = b"From 1111111111111111111111111111111111111111 Mon Sep 17 00:00:00 2001\nSubject: [PATCH] demo\n\ndiff --git a/demo.c b/demo.c\n--- a/demo.c\n+++ b/demo.c\n@@ -1 +1 @@\n-old\n+new\n"


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
