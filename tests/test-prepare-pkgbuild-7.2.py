#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "automation/prepare-pkgbuild-7.2.py"
SPEC = importlib.util.spec_from_file_location("prepare_pkgbuild_72", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SAMPLE = '''pkgbase=linux-charcoal-616
_nepbase=linux-neptune-616
_tag=6.16.12-valve27
source=(
  config
  latest-adios.patch
  latest-adios-default.patch
  latest-bore.patch
  latest-bore-sched-ext-coexistence-fix.patch
  latest-zen-01.patch
  latest-poc-selector.patch
)
prepare() {
  if [[ $src == latest-poc-selector.patch ]]; then :; fi
}
'''


class TransformTests(unittest.TestCase):
    def test_transforms_identifiers_and_patch_order(self) -> None:
        result = MODULE.transform(SAMPLE)
        MODULE.validate(result)
        self.assertIn("pkgbase=linux-charcoal-72", result)
        positions = [result.index(name) for name in MODULE.PATCH_ORDER]
        self.assertEqual(positions, sorted(positions))

    def test_is_idempotent(self) -> None:
        once = MODULE.transform(SAMPLE)
        twice = MODULE.transform(once)
        self.assertEqual(once, twice)

    def test_missing_patch_is_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.TransformError, "missing patch"):
            MODULE.transform(SAMPLE.replace("  latest-adios.patch\n", ""))


if __name__ == "__main__":
    unittest.main()
