#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "automation/port-poc-selector.py"
PATCH = ROOT / "6.16-poc-selector-v2.6.1r2.patch"

spec = importlib.util.spec_from_file_location("port_poc_selector", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PocPortTests(unittest.TestCase):
    def test_reviewed_patch_is_adapted_for_bore_layout(self) -> None:
        patch_text = PATCH.read_text(encoding="utf-8")
        adapted = module.adapt_patch(patch_text)
        self.assertNotIn(module.HUNK_HEADER, adapted)
        self.assertNotIn("poc_idle_committed", adapted)
        self.assertIn("@@ -2197,6 +2200,112 @@", adapted)

        sched_h = (
            "struct rq {\n"
            "#ifdef CONFIG_NO_HZ_COMMON\n"
            "\tunsigned long nohz_flags;\n"
            "#endif /* CONFIG_NO_HZ_COMMON */\n"
            "\n"
            "\tunsigned int\t\tttwu_pending;\n"
            "#ifdef CONFIG_SCHED_BORE\n"
            "\tstruct bore_ctx bore;\n"
            "#endif\n"
            "\tu64\t\t\tnr_switches;\n"
            "};\n"
        )
        result = module.adapt_sched_header(sched_h)
        expected = (
            "\tunsigned int\t\tttwu_pending;\n"
            "#ifdef CONFIG_SCHED_POC_SELECTOR\n"
            "\tunsigned int\t\tpoc_idle_committed;\n"
            "#endif\n"
            "#ifdef CONFIG_SCHED_BORE\n"
        )
        self.assertIn(expected, result)
        self.assertEqual(result.count("poc_idle_committed"), 1)

    def test_adapter_rejects_an_unreviewed_patch(self) -> None:
        changed = PATCH.read_text(encoding="utf-8").replace(
            "unsigned int\t\tpoc_idle_committed",
            "unsigned long\t\tpoc_idle_committed",
            1,
        )
        with self.assertRaises(module.PortError):
            module.adapt_patch(changed)

    def test_adapter_rejects_ambiguous_kernel_anchor(self) -> None:
        with self.assertRaises(module.PortError):
            module.adapt_sched_header(
                "unsigned int ttwu_pending;\nunsigned int ttwu_pending;\n"
            )


if __name__ == "__main__":
    unittest.main()
