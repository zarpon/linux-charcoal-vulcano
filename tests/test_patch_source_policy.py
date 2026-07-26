#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "automation/patch-sources.json").read_text(encoding="utf-8"))
PKGBUILD = (ROOT / "PKGBUILD").read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location(
    "charcoal_patch_resolver", ROOT / "automation/resolve-latest-patches.py"
)
assert spec and spec.loader
resolver = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = resolver
spec.loader.exec_module(resolver)

LOCAL_ONLY_PATCHES = {
    "vangogh_allow_higher_cpu_freq.patch",
    "vangogh_higher_max_power_limit.patch",
}


def components() -> list[dict[str, object]]:
    return [*MANIFEST["components"], *MANIFEST["auxiliary_components"]]


def source_lines(text: str) -> list[str]:
    start, end = resolver.find_array_bounds(text, "source")
    return [
        resolver.normalized_source_line(line)
        for line in text[start:end].splitlines()[1:-1]
        if line.strip() and not line.lstrip().startswith("#")
    ]


class PatchSourcePolicyTests(unittest.TestCase):
    def test_manifest_names_targets_and_source_matchers_are_unique(self) -> None:
        items = components()
        self.assertEqual(len({item["name"] for item in items}), len(items))
        self.assertEqual(len({item["target"] for item in items}), len(items))

        lines = source_lines(PKGBUILD)
        for item in items:
            matches = [
                line
                for line in lines
                if line == item["target"]
                or re.fullmatch(str(item["source_regex"]), line)
            ]
            self.assertEqual(matches, matches[:1], item["name"])
            self.assertEqual(len(matches), 1, item["name"])

    def test_every_applied_remote_patch_is_resolved_and_locked(self) -> None:
        items = components()
        for line in source_lines(PKGBUILD):
            local_name = line.split("::", 1)[0]
            remote_patch = ".patch" in line and (
                "http://" in line or "https://" in line
            )
            local_patch = (
                "://" not in line
                and line.endswith(".patch")
                and local_name not in LOCAL_ONLY_PATCHES
            )
            if not (remote_patch or local_patch):
                continue
            matches = [
                item["name"]
                for item in items
                if line == item["target"]
                or re.fullmatch(str(item["source_regex"]), line)
            ]
            self.assertEqual(len(matches), 1, f"unmanaged patch source: {line}")

    def test_latest_policy_ranks_project_version_before_kernel_filename(self) -> None:
        older = resolver.Candidate(
            "patches/testing/0001-linux6.19-bore-6.8.0.patch",
            "a" * 40,
            "https://example.invalid/older.patch",
            0,
            (6, 19),
            "6.8.0",
        )
        newer = resolver.Candidate(
            "patches/testing/0001-linux6.18-bore-6.9.0.patch",
            "b" * 40,
            "https://example.invalid/newer.patch",
            0,
            (6, 18),
            "6.9.0",
        )
        self.assertIs(max([older, newer], key=resolver.latest_key), newer)

    def test_zram_policy_tracks_separate_ir_and_lz4kdr_components(self) -> None:
        zram_ir = next(
            item for item in MANIFEST["components"] if item["name"] == "zram_ir"
        )
        lz4kdr = next(
            item for item in MANIFEST["components"] if item["name"] == "lz4kdr"
        )
        zram_ir_source = re.compile(str(zram_ir["source_regex"]))
        zram_ir_filename = re.compile(str(zram_ir["filename_regex"]))
        lz4kdr_source = re.compile(str(lz4kdr["source_regex"]))
        lz4kdr_filename = re.compile(str(lz4kdr["filename_regex"]))

        self.assertTrue(
            zram_ir_source.fullmatch("0001-linux6.16.12-zram-ir-1.2.patch")
        )
        self.assertFalse(
            zram_ir_source.fullmatch("0001-linux6.16.12-lz4kdr-1.3.patch")
        )
        self.assertTrue(
            zram_ir_filename.fullmatch("patches/0001-linux6.16.0-zram-ir-1.2.patch")
        )
        self.assertFalse(
            zram_ir_filename.fullmatch("patches/0001-linux6.12.74-lz4kdr-1.3.patch")
        )
        self.assertTrue(
            lz4kdr_source.fullmatch("0001-linux6.16.12-lz4kdr-1.3.patch")
        )
        self.assertFalse(
            lz4kdr_source.fullmatch("0001-linux6.16.12-zram-ir-1.2.patch")
        )
        self.assertTrue(
            lz4kdr_filename.fullmatch("patches/0001-linux6.12.74-lz4kdr-1.3.patch")
        )
        self.assertFalse(
            lz4kdr_filename.fullmatch("patches/0001-linux6.16.0-zram-ir-1.2.patch")
        )

        candidates = [
            resolver.Candidate(
                "patches/0001-linux6.12.74-lz4kdr-1.3.patch",
                "a" * 40,
                "https://example.invalid/nearest.patch",
                0,
                (6, 12, 74),
                "1.3",
            ),
            resolver.Candidate(
                "patches/0001-linux6.16.0-lz4kdr-1.3.patch",
                "b" * 40,
                "https://example.invalid/compatible.patch",
                2,
                (6, 16, 0),
                "1.3",
            ),
        ]
        compatible = [candidate for candidate in candidates if candidate.compatibility >= 2]
        self.assertEqual(
            max(compatible, key=resolver.compatible_key).path,
            "patches/0001-linux6.16.0-lz4kdr-1.3.patch",
        )
        self.assertEqual(
            resolver.nearest_candidate([candidates[0]], "6.16.12").path,
            "patches/0001-linux6.12.74-lz4kdr-1.3.patch",
        )

    def test_generic_source_rewrite_materializes_every_target(self) -> None:
        items = components()
        replacements = {str(item["name"]): str(item["target"]) for item in items}
        updated = resolver.replace_source_entries(PKGBUILD, items, replacements)
        lines = source_lines(updated)
        for target in replacements.values():
            self.assertEqual(lines.count(target), 1, target)

    def test_fixture_run_writes_complete_lock_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "automation").mkdir()
            (root / "automation/patch-sources.json").write_text(
                json.dumps(MANIFEST), encoding="utf-8"
            )
            (root / "PKGBUILD").write_text(PKGBUILD, encoding="utf-8")
            fixture: dict[str, object] = {
                "kernel_tag": "6.16.12-valve999",
                "kernel_sha": "f" * 40,
                "components": {},
                "auxiliary_components": {},
            }
            for group in ("components", "auxiliary_components"):
                selected: dict[str, object] = {}
                for index, item in enumerate(MANIFEST[group], 1):
                    selected[str(item["name"])] = {
                        "repository": str(item.get("repository", "fixture/source")),
                        "path": f"patches/{item['name']}.patch",
                        "commit": f"{index:040x}"[-40:],
                        "url": f"https://example.invalid/{item['name']}.patch",
                        "origin": "upstream-compatible",
                        "selection": "fixture",
                        "content": f"fixture patch {item['name']}\n",
                    }
                fixture[group] = selected
            fixture_path = root / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            previous = Path.cwd()
            try:
                import os
                os.chdir(root)
                saved = sys.argv
                sys.argv = [
                    "resolve-latest-patches.py",
                    "--fixture", str(fixture_path),
                    "--write",
                ]
                try:
                    with redirect_stdout(StringIO()):
                        self.assertEqual(resolver.main(), 0)
                finally:
                    sys.argv = saved
            finally:
                os.chdir(previous)

            lock = json.loads((root / "logs/patch-lock.json").read_text())
            self.assertEqual(lock["schema"], 3)
            self.assertEqual(
                set(lock["components"]),
                {item["name"] for item in MANIFEST["components"]},
            )
            self.assertEqual(
                set(lock["auxiliary_components"]),
                {item["name"] for item in MANIFEST["auxiliary_components"]},
            )


if __name__ == "__main__":
    unittest.main()
