#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "automation/prepare-steamos-7.2.py"
SPEC = importlib.util.spec_from_file_location("prepare_steamos_72", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class VersionTests(unittest.TestCase):
    def test_package_version_maps_to_valve_tag(self) -> None:
        self.assertEqual(
            MODULE.package_version_to_tag("7.2.0.rc3.valve.beta1"),
            "7.2.0-rc3-valve-beta1",
        )
        self.assertEqual(
            MODULE.package_version_to_tag("7.2.0.valve2"),
            "7.2.0-valve2",
        )

    def test_new_package_revision_wins(self) -> None:
        html = """
        <a href='linux-neptune-72-7.2.0.rc3.valve.beta1-1.src.tar.gz'>old</a>
        <a href='linux-neptune-72-7.2.0.rc3.valve.beta1-2.src.tar.gz'>new</a>
        """
        selected = MODULE.newest_package(MODULE.packages_from_html(html))
        self.assertEqual(selected.pkgrel, 2)

    def test_final_release_outranks_release_candidate(self) -> None:
        html = """
        <a href='linux-neptune-72-7.2.0.rc9.valve.beta9-9.src.tar.gz'>rc</a>
        <a href='linux-neptune-72-7.2.0.valve1-1.src.tar.gz'>stable</a>
        """
        selected = MODULE.newest_package(MODULE.packages_from_html(html))
        self.assertEqual(selected.pkgver, "7.2.0.valve1")

    def test_generated_manifest_pins_officially_selected_tag_and_series(self) -> None:
        package = MODULE.NeptunePackage(
            "linux-neptune-72-7.2.0.rc3.valve.beta1-2.src.tar.gz",
            "7.2.0.rc3.valve.beta1",
            2,
            "https://example.invalid/source.tar.gz",
        )
        manifest = MODULE.generated_manifest({"schema": 2, "components": []}, package)
        source = manifest["kernel_source"]
        self.assertEqual(source["series"], "7.2")
        self.assertEqual(source["preferred_tag"], "7.2.0-rc3-valve-beta1")
        self.assertTrue(source["allow_prerelease"])


class ConfigExtractionTests(unittest.TestCase):
    def test_extracts_shallow_arch_config(self) -> None:
        base = b"CONFIG_64BIT=y\nCONFIG_X86_64=y\n" + b"# filler\n" * 7000
        nested = b"CONFIG_64BIT=y\nCONFIG_X86_64=y\n" + b"nested\n" * 7000
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, data in (
                ("linux-neptune-72/src/linux/config", nested),
                ("linux-neptune-72/config", base),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        buffer.seek(0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "config"
            member = MODULE.extract_config_from_tar(buffer, out)
            self.assertEqual(member, "linux-neptune-72/config")
            self.assertEqual(out.read_bytes(), base)

    def test_rejects_archive_without_x86_config(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            data = b"not a kernel config" * 4000
            info = tarfile.TarInfo("pkg/config")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        buffer.seek(0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(MODULE.PrepareError, "usable Arch/Valve x86_64 config"):
                MODULE.extract_config_from_tar(buffer, Path(tmp) / "config")


if __name__ == "__main__":
    unittest.main()
