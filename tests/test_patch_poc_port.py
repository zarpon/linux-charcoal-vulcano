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


    def test_native_72_rebases_bore_overlaps_without_dropping_poc_fields(self) -> None:
        native_patch = """diff --git a/include/linux/sched.h b/include/linux/sched.h
--- a/include/linux/sched.h
+++ b/include/linux/sched.h
@@ -823,6 +823,17 @@ struct kmap_ctrl {
 #endif
 };
 
+#ifdef CONFIG_SCHED_POC_SELECTOR
+/* Learned WF_SYNC honesty of a waker, see kernel/sched/fair.c */
+struct poc_sync {
+	u64				mark;		/* own exec at the pending sync wake + 1, 0 = none */
+	u8				hist;		/* last 8 resolved sync wakes, bit = 1: a lie */
+	u8				explore;	/* waker's-CPU verdicts since the last exploration */
+	bool				on_waker_cpu;	/* pending wake put its wakee on our CPU */
+	bool				nopreempt;	/* as a wakee: must not preempt its waker */
+};
+#endif
+
 struct task_struct {
 #ifdef CONFIG_THREAD_INFO_IN_TASK
 	/*
diff --git a/kernel/sched/fair.c b/kernel/sched/fair.c
--- a/kernel/sched/fair.c
+++ b/kernel/sched/fair.c
@@ -1262,7 +1263,7 @@ static bool update_deadline(struct cfs_rq *cfs_rq, struct sched_entity *se)
 
 #include "pelt.h"
 
-static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu);
+static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, int sync);
 static unsigned long task_h_load(struct task_struct *p);
 static unsigned long capacity_of(int cpu);
 
@@ -8043,6 +8099,10 @@ static bool dequeue_task_fair(struct rq *rq, struct task_struct *p, int flags)
 	if (!p->se.sched_delayed)
 		util_est_dequeue(&rq->cfs, p);
 
+#ifdef CONFIG_SCHED_POC_SELECTOR
+	if (flags & DEQUEUE_SLEEP)
+		poc_sync_note_sleep(p);
+#endif
 	if (dequeue_entities(rq, &p->se, flags) < 0)
 		return false;
 
diff --git a/kernel/sched/sched.h b/kernel/sched/sched.h
--- a/kernel/sched/sched.h
+++ b/kernel/sched/sched.h
@@ -1177,6 +1177,11 @@ struct rq {
 	call_single_data_t	nohz_csd;
 #endif /* CONFIG_NO_HZ_COMMON */
 
+#ifdef CONFIG_SCHED_POC_SELECTOR
+	unsigned int		poc_idle_committed;
+	u64			poc_busy_bit;	/* lazy commit: pre-shifted busy bit (0 = idle), lazy mode */
+#endif
+
 #ifdef CONFIG_UCLAMP_TASK
 	struct uclamp_rq	uclamp[UCLAMP_CNT] ____cacheline_aligned;
"""
        include_source = """#ifdef CONFIG_SCHED_BORE
struct bore_ctx {
	bool stop_update;
};
#endif /* CONFIG_SCHED_BORE */

struct task_struct {
#ifdef CONFIG_THREAD_INFO_IN_TASK
	/*
"""
        fair_source = """
#include "pelt.h"

static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu);
static unsigned long task_h_load(struct task_struct *p);
static unsigned long capacity_of(int cpu);

static bool dequeue_task_fair(struct rq *rq, struct task_struct *p, int flags)
{
	if (!p->se.sched_delayed)
		util_est_dequeue(&rq->cfs, p);

#ifdef CONFIG_SCHED_BORE
	struct cfs_rq *cfs_rq = cfs_rq_of(&p->se);
#endif /* CONFIG_SCHED_BORE */
	if (dequeue_entities(rq, &p->se, flags) < 0)
		return false;
}
"""
        sched_source = """struct rq {
#ifdef CONFIG_NO_HZ_COMMON
	unsigned int		nohz_tick_stopped;
	call_single_data_t	nohz_csd;
#endif /* CONFIG_NO_HZ_COMMON */

#ifdef CONFIG_UCLAMP_TASK
	struct uclamp_rq	uclamp[UCLAMP_CNT] ____cacheline_aligned;
"""
        adapted = module.adapt_patch(
            native_patch, fair_source, sched_source, include_source
        )
        self.assertIn("struct poc_sync", adapted)
        self.assertIn("poc_sync_note_sleep(p);", adapted)
        self.assertIn("poc_idle_committed", adapted)
        self.assertIn("poc_busy_bit", adapted)
        self.assertIn("#ifdef CONFIG_SCHED_BORE", adapted)
        self.assertIn("NO_HZ", adapted)
        native_decl = (
            '-static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu);\n'
            '+static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, int sync);\n'
        )
        self.assertIn(native_decl, adapted)
        self.assertNotIn(' #include "pelt.h"\n #ifdef CONFIG_SMP\n', adapted)

    def test_v300_ports_only_wakeup_class_guard_overlap(self) -> None:
        before = (
            module.FAIR_SECTION_HEADER
            + "--- a/kernel/sched/fair.c\n+++ b/kernel/sched/fair.c\n"
            + "@@ -9781,6 +9871,10 @@ static void wakeup_preempt_fair\n"
        )
        body = (
            module.V300_NATIVE_WAKEUP_PREFIX
            + module.V300_WAKEE_WAITS_ADDITIONS
            + module.patch_context(module.V300_WAKEUP_SUFFIX)
        )
        after = "diff --git a/kernel/sched/idle.c b/kernel/sched/idle.c\n"
        patch = before + body + after
        source = module.V300_BORE_WAKEUP_PREFIX + module.V300_WAKEUP_SUFFIX
        adapted = module.adapt_native_72_v300_wakeup_overlap(patch, source)
        self.assertEqual(adapted.count(module.V300_WAKEE_WAITS_ADDITIONS), 1)
        self.assertIn(module.patch_context(module.V300_BORE_WAKEUP_PREFIX), adapted)
        self.assertTrue(adapted.endswith(after))
        with self.assertRaises(module.PortError):
            module.adapt_native_72_v300_wakeup_overlap(patch, source + source)
        with self.assertRaises(module.PortError):
            module.adapt_native_72_v300_wakeup_overlap(
                patch.replace("+\t\treturn;", "+\t\treturn false;"), source
            )


if __name__ == "__main__":
    unittest.main()
