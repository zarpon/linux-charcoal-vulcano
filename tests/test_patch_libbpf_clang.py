#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "automation/fix-libbpf-clang-warning.py"

spec = importlib.util.spec_from_file_location("fix_libbpf_clang", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class LibbpfClangCompatibilityTests(unittest.TestCase):
    def test_upstream_v2_guards_are_preserved_unchanged(self) -> None:
        source = f"{module.UPSTREAM_PUSH}\nint value;\n{module.UPSTREAM_POP}\n"
        self.assertEqual(module.adapt(source), source)

    def test_partial_or_duplicated_upstream_v2_guards_fail_closed(self) -> None:
        for source in (
            f"{module.UPSTREAM_PUSH}\nint value;\n#pragma GCC diagnostic pop\n",
            f"{module.UPSTREAM_POP}\nint value;\n{module.UPSTREAM_PUSH}\n",
            f"{module.UPSTREAM_PUSH}\n{module.UPSTREAM_PUSH}\n{module.UPSTREAM_POP}\n",
        ):
            with self.subTest(source=source), self.assertRaises(module.CompatibilityError):
                module.adapt(source)

    def test_current_gcc_pragma_is_guarded_from_clang(self) -> None:
        source = (
            "#pragma GCC diagnostic push\n"
            f"{module.PRAGMA}\n"
            "int value;\n"
            "#pragma GCC diagnostic pop\n"
        )
        adapted = module.adapt(source)
        self.assertEqual(adapted.count(module.GUARDED), 1)
        self.assertEqual(adapted.count(module.PRAGMA), 1)
        self.assertIn("#if !defined(__clang__)", adapted)

    def test_unexpected_upstream_structure_is_rejected(self) -> None:
        with self.assertRaises(module.CompatibilityError):
            module.adapt(f"{module.PRAGMA}\n{module.PRAGMA}\n")

    def test_double_application_is_rejected(self) -> None:
        with self.assertRaises(module.CompatibilityError):
            module.adapt(f"{module.GUARDED}\n")


if __name__ == "__main__":
    unittest.main()
