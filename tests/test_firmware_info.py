#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("firmware_info", ROOT / "automation/configure-firmware-info.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)

SOURCE = '''ret = _request_firmware_prepare(&fw, name, device, buf, size,
                                      offset, opt_flags);
#ifdef CONFIG_GENTOO_PRINT_FIRMWARE_INFO
        printk(KERN_NOTICE "Loading firmware: %s\\n", name);
#endif
if (ret <= 0)
        goto out;
'''


class FirmwareInfoTests(unittest.TestCase):
    def fixture(self, directory: str, source: str = SOURCE) -> tuple[Path, Path]:
        tree = Path(directory)
        loader = tree / "drivers/base/firmware_loader"
        loader.mkdir(parents=True)
        (loader / "main.c").write_text(source)
        kconfig = loader / "Kconfig"
        kconfig.write_text('config FW_LOADER\n\ttristate "Firmware loading"\n\nif FW_LOADER\n\nconfig FW_UPLOAD\n\tbool\n\nendif\n')
        return tree, kconfig

    def test_declares_switch_inside_loader_and_preserves_upstream_source(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, kconfig = self.fixture(directory)
            module.configure(tree)
            first = kconfig.read_text()
            self.assertIn("if FW_LOADER\n\nconfig GENTOO_PRINT_FIRMWARE_INFO\n", first)
            self.assertEqual((tree / "drivers/base/firmware_loader/main.c").read_text(), SOURCE)
            module.configure(tree)
            self.assertEqual(kconfig.read_text(), first)

    def test_missing_upstream_patch_fails_before_changing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, kconfig = self.fixture(directory, "/* unpatched source */\n")
            before = kconfig.read_text()
            with self.assertRaisesRegex(ValueError, "must be applied first"):
                module.configure(tree)
            self.assertEqual(kconfig.read_text(), before)

    def test_unknown_existing_switch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            tree, kconfig = self.fixture(directory)
            kconfig.write_text(kconfig.read_text() + "config GENTOO_PRINT_FIRMWARE_INFO\n\tint\n")
            with self.assertRaisesRegex(ValueError, "unexpected existing"):
                module.configure(tree)


if __name__ == "__main__":
    unittest.main()
