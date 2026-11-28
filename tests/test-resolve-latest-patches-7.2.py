#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
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
        self.assertIsNone(cpu.get("local_port"))

    def test_clang_polly_requires_explicit_71_to_72_port(self) -> None:
        manifest = json.loads((ROOT / "automation/patch-sources.json").read_text(encoding="utf-8"))
        override = ROOT / "automation/patch-source-overrides-7.2.json"
        MODULE.apply_overrides(manifest, override)
        polly = next(
            item for item in manifest["auxiliary_components"]
            if item["name"] == "clang_polly"
        )
        self.assertEqual(polly["port_for_kernel"], "7.2")
        self.assertTrue(polly["port_when_incompatible"])
        self.assertEqual(
            polly["local_port"],
            "7.2-clang-polly-from-cachyos-7.1.patch",
        )
        self.assertEqual(
            polly["local_port_upstream_sha256"],
            "71e5926efc30833a6fd756b9358529ac695fa688ae71cd74e31dd274ae1ecf05",
        )
        port = (ROOT / polly["local_port"]).read_text(encoding="utf-8")
        self.assertIn("Upstream: CachyOS/kernel-patches 7.1/misc/0001-clang-polly.patch", port)
        self.assertIn("Port-Target: evlaV/linux-integration 7.2.0-rc3-valve-beta1", port)


class ExactKernelSelectionTests(unittest.TestCase):
    def test_resolution_prefers_exact_valve_patchlevel_within_latest_release(self) -> None:
        component = {
            "name": "demo", "kind": "github_tree", "repository": "example/demo",
            "target": "latest-demo.patch", "source_regex": r"latest-demo\.patch",
            "filename_regex": r"^patches/linux7\.2\.\d+-demo-2\.0\.patch$",
            "kernel_version_regex": r"linux(?P<kernel>\d+\.\d+\.\d+)",
            "project_version_regex": r"demo-(?P<version>2\.0)\.patch$",
        }
        manifest = {
            "schema": 4,
            "kernel_source": {"repository": "evlaV/linux-integration", "series": "7.2",
                              "tag_regex": r"(?P<version>7\.2\.\d+)-valve2"},
            "components": [component], "auxiliary_components": [],
        }
        tree = {"tree": [{"type": "blob", "path": f"patches/linux7.2.{level}-demo-2.0.patch"}
                         for level in (7, 9)]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps(manifest))
            (root / "PKGBUILD").write_text(
                "_tag=old\nsource=(\n latest-demo.patch\n)\nsha256sums=(\n 'SKIP'\n)\n"
            )
            with (
                mock.patch.object(MODULE.Path, "cwd", return_value=root),
                mock.patch.object(sys, "argv", ["resolver", "--manifest", "manifest.json"]),
                mock.patch.object(MODULE, "preferred_kernel_tag", return_value=("7.2.7-valve2", "b" * 40)),
                mock.patch.object(MODULE.BASE, "repository_tree", return_value=("a" * 40, tree)),
                mock.patch.object(MODULE.BASE, "request_bytes", return_value=b"diff --git a/demo.c b/demo.c\n"),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(MODULE.main(), 0)
            lock = json.loads((root / "logs/patch-lock.json").read_text())
        self.assertEqual(lock["components"]["demo"]["kernel_version"], "7.2.7")
        self.assertEqual(lock["components"]["demo"]["selection"], "latest-native-series")

    def test_release_candidate_keeps_numeric_patchlevel(self) -> None:
        self.assertEqual(MODULE.patch_kernel_version("7.2.0-rc3-valve-beta1", "7.2"), "7.2.0")

    def test_tag_from_another_series_fails_closed(self) -> None:
        with self.assertRaisesRegex(MODULE.Resolve72Error, "does not match"):
            MODULE.patch_kernel_version("7.3.1-valve2", "7.2")


class CurrentAdiosNamingTests(unittest.TestCase):
    def test_all_policies_discover_v4_testing_release_and_require_its_port(self) -> None:
        paths = (
            "patches/stable/0001-linux7.2.7-ADIOS-3.3.0r3.patch",
            "patches/testing/0001-6.18.3-adios-v4.0.0-rc1.patch",
            "patches/testing/0001-6.12.44-adios-v4.0.0-rc1.patch",
        )
        tree = {"tree": [{"type": "blob", "path": path} for path in paths]}
        for override in (None, "patch-source-overrides.json", "patch-source-overrides-7.2.json"):
            manifest = json.loads((ROOT / "automation/patch-sources.json").read_text())
            if override:
                MODULE.apply_overrides(manifest, ROOT / "automation" / override)
            spec = next(item for item in manifest["components"] if item["name"] == "adios")
            with (
                self.subTest(override=override),
                mock.patch.object(MODULE.BASE, "repository_tree", return_value=("a" * 40, tree)),
                mock.patch.object(MODULE.BASE, "request_bytes", return_value=b"diff --git a/demo.c b/demo.c\n"),
            ):
                selected = MODULE.BASE.resolve_github_component(spec, "7.2.7", None, ROOT)
                self.assertEqual(selected["project_version"], "4.0.0-rc1")
                self.assertEqual(selected["kernel_version"], "6.18.3")
                self.assertEqual(selected["origin"], "adaptive-port")
                self.assertEqual(selected["latest_upstream_project_version"], "4.0.0-rc1")


if __name__ == "__main__":
    unittest.main()
