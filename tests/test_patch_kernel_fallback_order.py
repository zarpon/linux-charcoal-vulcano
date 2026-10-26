#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "automation/audit-latest-patch-versions.py"
SPEC = importlib.util.spec_from_file_location("charcoal_patch_audit_order_test", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def candidate(path: str, kernel: tuple[int, ...], project: str | None = None):
    return MODULE.resolver.Candidate(
        path=path,
        sha=(path.encode().hex() + "0" * 40)[:40],
        url=f"https://example.invalid/{path}",
        compatibility=0,
        kernel_version=kernel,
        project_version=project,
    )


class KernelFallbackOrderingTests(unittest.TestCase):
    def select(self, kernels, target="7.2.0"):
        selected = MODULE.nearest_candidate_chronological(kernels, target)
        self.assertIsNotNone(selected)
        return selected

    def test_7_1_is_closer_to_7_2_than_6_x(self) -> None:
        selected = self.select([
            candidate("linux-6.19.patch", (6, 19)),
            candidate("linux-7.1.patch", (7, 1)),
            candidate("linux-6.12.patch", (6, 12)),
        ])
        self.assertEqual(selected.kernel_version, (7, 1))

    def test_adios_6_19_is_closer_than_6_12(self) -> None:
        selected = self.select([
            candidate("adios-6.12.44.patch", (6, 12, 44), "3.2.0"),
            candidate("adios-6.19.3.patch", (6, 19, 3), "3.2.0"),
        ])
        self.assertEqual(selected.kernel_version, (6, 19, 3))

    def test_fsync_6_11_is_closer_than_6_3(self) -> None:
        selected = self.select([
            candidate("fsync-6.3.patch", (6, 3)),
            candidate("fsync-6.11.patch", (6, 11)),
        ])
        self.assertEqual(selected.kernel_version, (6, 11))

    def test_same_major_selection_remains_numeric(self) -> None:
        selected = self.select([
            candidate("linux-6.12.patch", (6, 12)),
            candidate("linux-6.17.patch", (6, 17)),
            candidate("linux-6.19.patch", (6, 19)),
        ], target="6.18.45")
        self.assertEqual(selected.kernel_version, (6, 19))


if __name__ == "__main__":
    unittest.main()
