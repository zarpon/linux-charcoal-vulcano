#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "automation/resolve-latest-patches-7.2.py"
SPEC = importlib.util.spec_from_file_location("resolve_latest_patches_72", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PreferredTagTests(unittest.TestCase):
    @staticmethod
    def config() -> dict[str, object]:
        return {
            "repository": "evlaV/linux-integration",
            "series": "7.2",
            "preferred_tag": "7.2.0-rc3-valve-beta1",
            "allow_prerelease": True,
            "tag_regex": (
                r"(?P<version>7\.2(?:\.[0-9]+)?(?:-rc[0-9]+)?)"
                r"-valve(?P<valve>.*)"
            ),
        }

    def test_resolves_and_peels_annotated_preferred_tag(self) -> None:
        refs = [{
            "ref": "refs/tags/7.2.0-rc3-valve-beta1",
            "object": {"sha": "a" * 40, "type": "tag", "url": "tag-url"},
        }]
        with mock.patch.object(MODULE.BASE, "request_json", side_effect=[refs, {"object": {"sha": "b" * 40}}]):
            name, sha = MODULE.preferred_kernel_tag(self.config(), None)
        self.assertEqual(name, "7.2.0-rc3-valve-beta1")
        self.assertEqual(sha, "b" * 40)

    def test_rejects_missing_official_tag(self) -> None:
        with mock.patch.object(MODULE.BASE, "request_json", return_value=[]):
            with self.assertRaisesRegex(MODULE.Resolve72Error, "absent upstream"):
                MODULE.preferred_kernel_tag(self.config(), None)

    def test_series_is_independent_from_rc_tag(self) -> None:
        self.assertEqual(MODULE.kernel_series({"kernel_source": self.config()}), "7.2")

    def test_cpu_optimizations_requires_explicit_72_compatibility_port(self) -> None:
        manifest = json.loads((ROOT / "automation/patch-sources.json").read_text(encoding="utf-8"))
        override = ROOT / "automation/patch-source-overrides-7.2.json"
        MODULE.apply_overrides(manifest, override)
        cpu = next(
            item for item in manifest["auxiliary_components"]
            if item["name"] == "cpu_optimizations"
        )
        self.assertEqual(cpu["port_for_kernel"], "7.2")
        self.assertTrue(cpu["port_when_incompatible"])
        self.assertEqual(
            cpu["adaptive_port"],
            "cpu-optimizations-6.16plus-to-valve-7.2",
        )
        self.assertNotIn("local_port", cpu)


if __name__ == "__main__":
    unittest.main()
