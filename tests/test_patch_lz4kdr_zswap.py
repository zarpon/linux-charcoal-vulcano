#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "0002-linux6.16.12-lz4kdr-zswap-1.0.patch"
PKGBUILD = (ROOT / "PKGBUILD").read_text(encoding="utf-8")


class Lz4kdrZswapPortTests(unittest.TestCase):
    def test_patch_is_locked_and_packaged_after_lz4kdr(self) -> None:
        self.assertTrue(PATCH.is_file())
        self.assertIn(
            "0001-linux6.16.12-lz4kdr-1.3.patch\n"
            "  0002-linux6.16.12-lz4kdr-zswap-1.0.patch",
            PKGBUILD,
        )
        expected = (
            "27220138dd604e3eb2c6d3cee029345335809853e51445b3e3115c615a8eb64f"
        )
        self.assertIn(f"'{expected}'", PKGBUILD)
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), expected)

    def test_patch_registers_acomp_without_touching_zram(self) -> None:
        text = PATCH.read_text(encoding="utf-8")
        paths = {
            match.group(1)
            for match in re.finditer(
                r"^diff --git a/([^ ]+) b/\1$", text, re.MULTILINE
            )
        }
        self.assertEqual(
            paths,
            {"crypto/Kconfig", "crypto/Makefile", "crypto/lz4kdr.c", "mm/Kconfig"},
        )
        for required in (
            "struct acomp_alg",
            "crypto_register_acomp",
            'cra_name\t\t= "lz4kdr"',
            "zswap.compressor=lz4kdr",
            "LZ4KDR_STATUS_INCOMPRESSIBLE",
        ):
            self.assertIn(required, text)
        self.assertNotIn("drivers/block/zram/", text)
        self.assertNotIn("lib/lz4kdr/", text)

    def test_zram_and_zswap_configuration_remain_separate(self) -> None:
        zram_config = (ROOT / "config-charcoal").read_text(encoding="utf-8")
        base_config = (ROOT / "config").read_text(encoding="utf-8")
        self.assertIn("CONFIG_CRYPTO_LZ4KDR=y", zram_config)
        self.assertIn("CONFIG_ZRAM_BACKEND_LZ4KDR=y", base_config)
        self.assertIn("CONFIG_ZRAM_BACKEND_ZSTD=y", base_config)
        self.assertIn('CONFIG_ZRAM_DEF_COMP="zstd"', base_config)
        self.assertIn("CONFIG_ZSWAP_COMPRESSOR_DEFAULT_ZSTD=y", base_config)
        self.assertIn('CONFIG_ZSWAP_COMPRESSOR_DEFAULT="zstd"', base_config)


if __name__ == "__main__":
    unittest.main()
