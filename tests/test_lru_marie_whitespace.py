#!/usr/bin/env python3
"""Regression tests for the LRU Marie vmscan whitespace normalizer."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "automation/fix-lru-marie-whitespace.py"
SPEC = importlib.util.spec_from_file_location("fix_lru_marie_whitespace", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LruMarieWhitespaceTests(unittest.TestCase):
    def test_normalizes_exact_upstream_indent_and_is_idempotent(self) -> None:
        source = "before\n" + MODULE.BAD + "\nafter\n"
        result = MODULE.normalize(source)
        self.assertEqual(result, "before\n" + MODULE.GOOD + "\nafter\n")
        self.assertEqual(MODULE.normalize(result), result)

    def test_result_passes_git_diff_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "vmscan.c"
            source.write_text("before\n" + MODULE.BAD + "\nafter\n")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "vmscan.c"], cwd=root, check=True)
            subprocess.run(
                [sys.executable, str(SCRIPT), str(source)], check=True,
                capture_output=True, text=True,
            )
            subprocess.run(["git", "diff", "--check"], cwd=root, check=True)

    def test_source_drift_fails_without_partial_write(self) -> None:
        changed = MODULE.BAD.replace("VM_EXEC", "VM_READ")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "vmscan.c"
            source.write_text(changed)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expected exactly one", result.stderr)
            self.assertEqual(source.read_text(), changed)


if __name__ == "__main__":
    unittest.main()
