#!/usr/bin/env python3
"""Keep 7.2's active patch stack while preventing stale 6.16 payloads."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNUSED_616_PATCHES = {
    "0001-linux6.16.12-zram-ir-1.2.patch",
    "6.16-nap-v0.5.0.patch",
    "6.16.12-ADIOS-3.2.0.patch",
    "6.16.12-amd-pstate-epp-boost-01-kernel-doc.port.patch",
    "6.16.12-amd-pstate-epp-boost-02-cache-order.port.patch",
    "6.16.12-amd-pstate-epp-boost-03-core.port.patch",
    "6.16.12-amd-pstate-epp-boost-04-docs.port.patch",
    "6.16.12-bore-6.8.0-rc1.patch",
    "6.16.12-bore-sched-ext-coexistence-fix.patch",
    "6.16.12-lru_marie-0.6.7.patch",
}
RETAINED_616_OVERLAY = "6.16.12-bore-6.8.0-final.patch"
ACTIVE_COMPONENTS = {
    "latest-adios.patch",
    "latest-adios-default.patch",
    "latest-bore.patch",
    "latest-bore-sched-ext-coexistence-fix.patch",
    "latest-lru_marie.patch",
    "latest-nap.patch",
    "latest-poc-selector.patch",
    "latest-zram-ir.patch",
    "latest-amd-pstate-epp-boost-01-kernel-doc.patch",
    "latest-amd-pstate-epp-boost-02-cache-order.patch",
    "latest-amd-pstate-epp-boost-03-core.patch",
    "latest-amd-pstate-epp-boost-04-docs.patch",
}


class UnusedPatchCleanupTests(unittest.TestCase):
    def test_all_unreferenced_616_payloads_are_removed(self) -> None:
        present = {path.name for path in ROOT.glob("*.patch")}
        self.assertFalse(UNUSED_616_PATCHES & present, sorted(UNUSED_616_PATCHES & present))

    def test_keeps_only_the_616_patch_still_referenced_by_policy(self) -> None:
        self.assertTrue((ROOT / RETAINED_616_OVERLAY).is_file())
        policy = json.loads(
            (ROOT / "automation/patch-source-overrides.json").read_text(encoding="utf-8")
        )
        self.assertIn(RETAINED_616_OVERLAY, policy["components"]["bore"]["local_port_overlays"])

    def test_dynamic_72_patch_families_remain_in_build_stack(self) -> None:
        pkgbuild = (ROOT / "PKGBUILD").read_text(encoding="utf-8")
        missing = sorted(name for name in ACTIVE_COMPONENTS if name not in pkgbuild)
        self.assertFalse(missing, missing)
        zram_patch = ROOT / "0001-linux7.2-zram-ir-1.2.patch"
        self.assertTrue(zram_patch.is_file())
        zram_text = zram_patch.read_text(encoding="utf-8")
        for expected in (
            "sysctl_zram_recomp_immediate = 1",
            '"zram_recomp_immediate"',
            "params->level = -1",
        ):
            self.assertIn(expected, zram_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
