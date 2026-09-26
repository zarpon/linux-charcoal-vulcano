#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "automation/port-poc-selector.py"

UPSTREAM_PATCH = """From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
Subject: [PATCH] 6.18.3-poc-selector-v2.6.3

diff --git a/kernel/sched/sched.h b/kernel/sched/sched.h
--- a/kernel/sched/sched.h
+++ b/kernel/sched/sched.h
@@ -1135,6 +1135,9 @@ struct rq {
 #endif /* CONFIG_NO_HZ_COMMON */

\tunsigned int\t\tttwu_pending;
+#ifdef CONFIG_SCHED_POC_SELECTOR
+\tunsigned int\t\tpoc_idle_committed;
+#endif
 \tu64\t\t\tnr_switches;
@@ -2197,6 +2200,112 @@ static inline struct task_group *task_group(struct task_struct *p)

#endif /* !CONFIG_CGROUP_SCHED */

+#ifdef CONFIG_SCHED_POC_SELECTOR
+extern struct static_key_true poc_selector_active;
+#endif
diff --git a/kernel/sched/fair.c b/kernel/sched/fair.c
--- a/kernel/sched/fair.c
+++ b/kernel/sched/fair.c
@@ -1064,7 +1065,7 @@ static bool update_deadline(struct cfs_rq *cfs_rq, struct sched_entity *se)
\x20
 #include "pelt.h"
\x20
-static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu);
+static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, int sync);
 static unsigned long task_h_load(struct task_struct *p);
 static unsigned long capacity_of(int cpu);
\x20
"""

FAIR_SOURCE = """
#include "pelt.h"
#ifdef CONFIG_SMP

static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu);
static unsigned long task_h_load(struct task_struct *p);
static unsigned long capacity_of(int cpu);

"""

SCHED_HEADER = """#ifdef CONFIG_SMP
\tunsigned int\t\tttwu_pending;
#endif
\tu64\t\t\tnr_switches;
"""

spec = importlib.util.spec_from_file_location("port_poc_selector", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PocPortTests(unittest.TestCase):
    def test_v300_sleep_hook_preserves_additions_at_valve_dequeue_entry(self) -> None:
        prefix = (
            "Subject: [PATCH] 6.18.3-poc-selector-v3.0.0\n"
            + module.FAIR_SECTION_HEADER
            + "--- a/kernel/sched/fair.c\n+++ b/kernel/sched/fair.c\n"
            + "@@ -7168,6 +7172,10 @@ static bool dequeue_task_fair\n"
        )
        suffix = "@@ -7601,6 +7609,20 @@ void __update_idle_core\n"
        patch = prefix + module.V300_SLEEP_CONTEXT + suffix
        adapted = module.adapt_v300_sleep_hunk(patch, module.VALVE_DEQUEUE_ANCHOR)
        self.assertIn("@@ -1,5 +5,9 @@", adapted)
        self.assertIn(" {\n" + module.V300_SLEEP_HOOK, adapted)
        self.assertTrue(adapted.endswith(suffix))
        self.assertEqual(adapted.count(module.V300_SLEEP_HOOK), 1)
        with self.assertRaises(module.PortError):
            module.adapt_v300_sleep_hunk(
                patch, module.VALVE_DEQUEUE_ANCHOR * 2
            )
        with self.assertRaises(module.PortError):
            module.adapt_v300_sleep_hunk(
                patch.replace("+\tif (flags & DEQUEUE_SLEEP)", "+\tif (flags)"),
                module.VALVE_DEQUEUE_ANCHOR,
            )

    def test_v300_wakeup_hook_preserves_both_poc_addition_blocks(self) -> None:
        prefix = (
            "Subject: [PATCH] 6.18.3-poc-selector-v3.0.0\n"
            + module.FAIR_SECTION_HEADER
            + "--- a/kernel/sched/fair.c\n+++ b/kernel/sched/fair.c\n"
            + "@@ -8745,7 +8836,15 @@ static void check_preempt_wakeup_fair\n"
        )
        suffix = "\ndiff --git a/kernel/sched/idle.c b/kernel/sched/idle.c\n"
        patch = prefix + module.V300_WAKEUP_BODY + suffix
        native_context = module.V300_WAKEUP_BODY.replace(
            " \tbool do_preempt_short = false;\n", ""
        )
        source = module.old_hunk_text(native_context)
        adapted = module.adapt_v300_wakeup_hunk(patch, source)
        additions = lambda value: [
            line for line in value.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        self.assertEqual(additions(patch), additions(adapted))
        self.assertNotIn("bool do_preempt_short", adapted)
        self.assertTrue(adapted.endswith(suffix))
        with self.assertRaises(module.PortError):
            module.adapt_v300_wakeup_hunk(patch, source * 2)

    def test_reviewed_patch_is_adapted_for_bore_layout(self) -> None:
        adapted = module.adapt_patch(UPSTREAM_PATCH, FAIR_SOURCE, SCHED_HEADER)
        adapted_sched = module.sched_section(adapted)
        self.assertEqual(adapted_sched.count("poc_idle_committed"), 1)
        self.assertIn("@@ -2197,6 +2200,112 @@", adapted_sched)
        self.assertIn(
            "@@ -1,8 +2,8 @@ static bool update_deadline",
            adapted,
        )
        self.assertIn(' #include "pelt.h"\n #ifdef CONFIG_SMP\n', adapted)
        self.assertIn(
            "+static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, int sync);",
            adapted,
        )
        self.assertIn("@@ -1,4 +1,7 @@ struct rq {", adapted)
        self.assertIn(module.FIELD_BLOCK, adapted)

    def test_adapter_rejects_an_unreviewed_patch(self) -> None:
        changed = UPSTREAM_PATCH.replace(
            "unsigned int\t\tpoc_idle_committed",
            "unsigned long\t\tpoc_idle_committed",
            1,
        )
        with self.assertRaises(module.PortError):
            module.adapt_patch(changed)

    def test_adapter_accepts_a_relocated_reviewed_sched_hunk(self) -> None:
        relocated = UPSTREAM_PATCH.replace(
            "@@ -1135,6 +1135,9 @@ struct rq {",
            "@@ -987,6 +987,9 @@ struct rq {",
        )
        adapted = module.adapt_patch(relocated, FAIR_SOURCE, SCHED_HEADER)
        self.assertIn("@@ -1,4 +1,7 @@ struct rq {", adapted)
        self.assertEqual(module.sched_section(adapted).count("poc_idle_committed"), 1)

    def test_adapter_rejects_ambiguous_kernel_anchor(self) -> None:
        with self.assertRaises(module.PortError):
            module.sched_hunk(SCHED_HEADER + SCHED_HEADER)

    def test_adapter_rejects_an_unreviewed_fair_hunk(self) -> None:
        changed = UPSTREAM_PATCH.replace(
            "static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, int sync);",
            "static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, bool sync);",
        )
        with self.assertRaises(module.PortError):
            module.adapt_patch(changed)

    def test_adapter_rejects_ambiguous_fair_context(self) -> None:
        with self.assertRaises(module.PortError):
            module.adapt_patch(UPSTREAM_PATCH, FAIR_SOURCE + FAIR_SOURCE)

    def test_adapter_rejects_a_previously_modified_kernel_header(self) -> None:
        with self.assertRaises(module.PortError):
            module.sched_hunk(SCHED_HEADER.replace("nr_switches", "poc_idle_committed"))

    def test_cli_generates_a_patch_without_mutating_the_kernel_header(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            upstream = root / "upstream.patch"
            output = root / "adapted.patch"
            sched_header = root / "sched.h"
            fair_source = root / "fair.c"
            upstream.write_text(UPSTREAM_PATCH, encoding="utf-8")
            sched_header.write_text(SCHED_HEADER, encoding="utf-8")
            fair_source.write_text(FAIR_SOURCE, encoding="utf-8")
            before = sched_header.read_bytes()

            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    str(upstream),
                    str(output),
                    str(sched_header),
                    str(fair_source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(sched_header.read_bytes(), before)
            self.assertNotIn(b"\r\n", output.read_bytes())
            self.assertIn("poc_idle_committed", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
