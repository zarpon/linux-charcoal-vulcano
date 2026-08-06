import importlib.util
import pathlib
import sys
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "automation" / "harden-actions-workflow.py"
SPEC = importlib.util.spec_from_file_location("harden_actions_workflow", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class HardeningTests(unittest.TestCase):
    def test_replaces_cancellation_based_group(self):
        content = f"name: build\n\n{MODULE.OLD_BLOCK}\njobs:\n  build: {{}}\n"
        updated, changed = MODULE.harden(content)
        self.assertTrue(changed)
        self.assertIn(MODULE.NEW_BLOCK, updated)
        self.assertNotIn(MODULE.OLD_BLOCK, updated)

    def test_is_idempotent(self):
        content = f"name: build\n\n{MODULE.NEW_BLOCK}\njobs:\n  build: {{}}\n"
        updated, changed = MODULE.harden(content)
        self.assertFalse(changed)
        self.assertEqual(updated, content)

    def test_rejects_unknown_concurrency_layout(self):
        with self.assertRaisesRegex(ValueError, "expected Charcoal concurrency block"):
            MODULE.harden("name: build\njobs: {}\n")


if __name__ == "__main__":
    unittest.main()
