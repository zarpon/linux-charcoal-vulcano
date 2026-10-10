#!/usr/bin/env python3
"""Exercise the configuration gate used by makepkg prepare(), without a build."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKGBUILD = ROOT / "PKGBUILD"
PREPARE_GATE = PKGBUILD.read_text().split("  _make_llvm olddefconfig\n", 1)[1].split(
    "  diff -u ../config .config", 1
)[0]


class KernelConfigValidationTests(unittest.TestCase):
    def setUp(self):
        # Kconfig derives the compressor string from the LZ4 choice. The other
        # inputs come from the same fragment that prepare() merges for the build.
        self.config = (ROOT / "config-charcoal").read_text()
        self.config += '\nCONFIG_ZSWAP_COMPRESSOR_DEFAULT="lz4"\n'

    def validate(self, config):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".config").write_text(config)
            return subprocess.run(
                ["bash", "-ec", 'source "$1"\n' + PREPARE_GATE, "test", str(PKGBUILD)],
                cwd=directory,
                capture_output=True,
                text=True,
            )

    def test_requested_defaults_pass_the_actual_prepare_gate(self):
        result = self.validate(self.config)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_defaults_fail_with_the_missing_setting(self):
        for setting in (
            "CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE_O3=y",
            "CONFIG_ZEN_INTERACTIVE=y",
            "CONFIG_ZSWAP=y",
            "CONFIG_ZSWAP_DEFAULT_ON=y",
            "CONFIG_ZSWAP_SHRINKER_DEFAULT_ON=y",
            "CONFIG_ZSWAP_COMPRESSOR_DEFAULT_LZ4=y",
            'CONFIG_ZSWAP_COMPRESSOR_DEFAULT="lz4"',
            "CONFIG_ZSMALLOC=y",
            "CONFIG_CRYPTO_LZ4=y",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, self.config)
                symbol = setting.split("=", 1)[0]
                result = self.validate(self.config.replace(setting, f"# {symbol} is not set"))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(setting, result.stderr)


if __name__ == "__main__":
    unittest.main()
