#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "automation/normalize-diff-whitespace.py"
SPEC = importlib.util.spec_from_file_location("normalize_diff_whitespace", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd, text=True, capture_output=True, check=True
    )


class NormalizeTests(unittest.TestCase):
    def repo(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="wsnorm-"))
        run("git", "init", "-q", cwd=root)
        run("git", "config", "user.email", "test@example.invalid", cwd=root)
        run("git", "config", "user.name", "test", cwd=root)
        (root / "sample.c").write_text("int base;\n", encoding="utf-8")
        run("git", "add", "sample.c", cwd=root)
        run("git", "commit", "-qm", "base", cwd=root)
        return root

    def test_normalizes_only_diff_check_errors(self) -> None:
        root = self.repo()
        (root / "sample.c").write_text(
            "int base;\n"
            "\tint clean;\n"
            "   \tint mixed;\n"
            "int trailing;   \n",
            encoding="utf-8",
        )
        before = MODULE.run_diff_check(root)
        self.assertNotEqual(before.returncode, 0)
        MODULE.normalize(root)
        after = MODULE.run_diff_check(root)
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
        text = (root / "sample.c").read_text(encoding="utf-8")
        self.assertIn("int mixed;", text)
        self.assertIn("int trailing;\n", text)
        self.assertNotIn("int trailing;   ", text)

    def test_clean_tree_is_noop(self) -> None:
        root = self.repo()
        self.assertEqual(MODULE.normalize(root), 0)
        self.assertEqual(
            run("git", "status", "--porcelain", cwd=root).stdout,
            "",
        )


if __name__ == "__main__":
    unittest.main()
