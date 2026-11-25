import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'charcoal_cast_port', ROOT / 'automation/port-lru-cast-latest.py')
cast_port = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cast_port
SPEC.loader.exec_module(cast_port)


VALVE_CORE = '''void sched_tick(void)
{
\tstruct rq *rq = cpu_rq(cpu);
\tstruct task_struct *curr, *donor;
\tcurr = rq->curr;
\tdonor = rq->donor;

\tpsi_account_irqtime(rq, donor, NULL);

\tupdate_rq_clock(rq);
}
'''

UPSTREAM_PATCH = '''diff --git a/kernel/sched/core.c b/kernel/sched/core.c
--- a/kernel/sched/core.c
+++ b/kernel/sched/core.c
@@ -8,6 +8,8 @@ void sched_tick(void)
 \tdonor = rq->donor;
 
 \tpsi_account_irqtime(rq, curr, NULL);
+\t/* a task that runs on without switching still sets young bits */
+\tlru_cast_use_mm(rq->curr->mm);
 
 \tupdate_rq_clock(rq);
 }
'''


class CastValveContextPortTests(unittest.TestCase):
    def test_valve_donor_context_is_reviewed_and_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'kernel/sched').mkdir(parents=True)
            (root / 'kernel/sched/core.c').write_text(VALVE_CORE)
            source = root / 'cast.patch'
            output = root / 'cast-prepared.patch'
            source.write_text(UPSTREAM_PATCH)

            result = cast_port.prepare(source, output, root)

            self.assertEqual(result, 'ported-valve-sched-tick-donor-context')
            prepared = output.read_text()
            self.assertIn('psi_account_irqtime(rq, donor, NULL);', prepared)
            subprocess.run(
                ['git', '-C', str(root), 'apply', '--recount', '--check', str(output)],
                check=True,
            )


    def test_valve_bridge_refuses_source_change_and_checks_core(self):
        a = """diff --git a/mm/lru_cast/version.h b/mm/lru_cast/version.h
new file mode 100644
--- /dev/null
+++ b/mm/lru_cast/version.h
@@ -0,0 +1 @@
+version
"""
        b = a.replace("+version", "+changed")
        self.assertEqual(cast_port.cast_core_additions(a)["mm/lru_cast/version.h"], "version")
        self.assertNotEqual(cast_port.cast_core_additions(a), cast_port.cast_core_additions(b))
        self.assertEqual(
            cast_port.git_blob_digest(b"abc"),
            __import__("hashlib").sha1(b"blob 3\0abc").hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "upstream source SHA"):
                cast_port.reviewed_valve_cast_bridge(b"untrusted", root, root / "out.patch")

    def test_reviewed_valve_rmap_preserves_switching_and_notifier(self):
        self.assertIn("!lru_gen_switching()", cast_port.CAST_VALVE_RMAP_PORT)
        self.assertIn("lru_gen_look_around(&pvmw, nr)", cast_port.CAST_VALVE_RMAP_PORT)
        self.assertIn("clear_flush_young_ptes_notify", cast_port.CAST_VALVE_RMAP_PORT)
        self.assertIn("lru_cast_look_around(&pvmw)", cast_port.CAST_VALVE_RMAP_PORT)


    def test_valve_vmscan_lock_wrapper_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mm").mkdir()
            (root / "mm/vmscan.c").write_text(
                "/* source fixture based on Valve 7.2.7 */\n"
                + cast_port.CAST_VALVE_VMSCAN_PREIMAGE + "\n"
            )
            upstream_section = (
                "diff --git a/mm/vmscan.c b/mm/vmscan.c\n"
                + cast_port.CAST_VALVE_VMSCAN_HUNK
                + "+\tif (lru_cast_on(lruvec))\n"
                + "+\t\tnr_taken = lru_cast_isolate_folios(nr_to_scan, lruvec, &folio_list,\n"
                + "+\telse\n"
                + "+\t\tnr_taken = isolate_lru_folios(nr_to_scan, lruvec, &folio_list,\n"
            )
            result = cast_port.adapt_valve_vmscan_lock_context(upstream_section, root)
            self.assertEqual(result.count(cast_port.CAST_VALVE_VMSCAN_PORT), 1)
            self.assertIn("+\t\tlru_cast_walk_ask();", result)
            self.assertIn("+\t\tnr_taken = lru_cast_isolate_folios", result)
            self.assertNotIn(" \tspin_lock_irq(&lruvec->lru_lock);", result)
            (root / "mm/vmscan.c").write_text("unreviewed locking API")
            with self.assertRaisesRegex(RuntimeError, "lock/API preimage changed"):
                cast_port.adapt_valve_vmscan_lock_context(upstream_section, root)
            (root / "mm/vmscan.c").write_text(cast_port.CAST_VALVE_VMSCAN_PREIMAGE)
            with self.assertRaisesRegex(RuntimeError, "source hunk changed"):
                cast_port.adapt_valve_vmscan_lock_context(
                    upstream_section.replace("lru_cast_walk_ask", "no_walk_ask"), root
                )
            with self.assertRaisesRegex(RuntimeError, "missing/duplicated"):
                cast_port.adapt_valve_vmscan_lock_context("", root)


    def test_valve_mm_contexts_keep_kernel_features_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}
            for name, official, adapted, preimage in cast_port.CAST_VALVE_MM_CONTEXTS:
                files.setdefault(name, []).append(preimage)
                self.assertNotEqual(official, adapted)
                self.assertIn("@@", adapted)
            for name, contents in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n/* isolated fixture */\n".join(contents))
            patch = "\n".join(
                official for _, official, _, _ in cast_port.CAST_VALVE_MM_CONTEXTS
            )
            result = cast_port.adapt_valve_mm_contexts(patch, root)
            self.assertIn("+\tif (lru_cast_add_folio", result)
            self.assertIn("VM_WARN_ON_ONCE_FOLIO(!folio_matches_lruvec", result)
            self.assertIn(" #include <linux/leafops.h>", result)
            self.assertIn("+#include <linux/kfifo.h>", result)
            with self.assertRaisesRegex(RuntimeError, "bridge hunk drift"):
                cast_port.adapt_valve_mm_contexts(
                    patch.replace("lru_cast_add_folio", "bad_cast_add"), root
                )
            (root / "mm/filemap.c").write_text("unreviewed Valve include layout")
            with self.assertRaisesRegex(RuntimeError, "target API preimage drift"):
                cast_port.adapt_valve_mm_contexts(patch, root)

    def test_valve_dryrun_failure_keeps_first_and_last_errors(self):
        out = subprocess.CompletedProcess(
            args=["patch"], returncode=1,
            stdout="can't create include/linux/mm_inline.h\n" + "ok\n" * 3000
                   + "checking mm/workingset.c\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            from unittest import mock
            with mock.patch.object(cast_port, "__file__", str(Path(directory) / "automation" / "port.py")):
                summary = cast_port.cast_dryrun_failure(out)
                self.assertIn("can't create include/linux/mm_inline.h", summary)
                self.assertIn("checking mm/workingset.c", summary)
                self.assertTrue((Path(directory) / "logs" / "cast-valve-dry-run.log").is_file())


    def test_valve_workingset_shadow_accounting_in_refault_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            (tree / "mm").mkdir()
            (tree / "mm/workingset.c").write_text(
                "static void lru_gen_refault(struct folio *folio, void *shadow)\n{\n"
                + cast_port.CAST_VALVE_WORKINGSET_PREIMAGE + "\n}\n"
            )
            upstream = (
                "diff --git a/mm/workingset.c b/mm/workingset.c\n"
                + cast_port.CAST_VALVE_WORKINGSET_HUNK
            )
            adapted = cast_port.adapt_valve_workingset_refault(upstream, tree)
            self.assertIn(cast_port.CAST_VALVE_WORKINGSET_PORT, adapted)
            self.assertIn("int type = folio_is_file_lru(folio);", adapted)
            self.assertIn("int delta = folio_nr_pages(folio);", adapted)
            self.assertIn("lru_cast_shadow(shadow)", adapted)
            self.assertIn("WORKINGSET_REFAULT_BASE + type, delta", adapted)
            self.assertIn("lru_gen_test_recent(shadow, &lruvec, &token, &workingset, type)", adapted)
            self.assertEqual(
                [line[1:] for line in cast_port.CAST_VALVE_WORKINGSET_HUNK.splitlines()
                 if line.startswith("+")],
                [line[1:] for line in cast_port.CAST_VALVE_WORKINGSET_PORT.splitlines()
                 if line.startswith("+")]
            )
            (tree / "mm/workingset.c").write_text("unreviewed scope")
            with self.assertRaisesRegex(RuntimeError, "scope/API drift"):
                cast_port.adapt_valve_workingset_refault(upstream, tree)
            (tree / "mm/workingset.c").write_text(
                cast_port.CAST_VALVE_WORKINGSET_PREIMAGE
            )
            with self.assertRaisesRegex(RuntimeError, "official hunk changed"):
                cast_port.adapt_valve_workingset_refault(
                    upstream.replace("lru_cast_shadow", "unreviewed_shadow"), tree
                )
            with self.assertRaisesRegex(RuntimeError, "section absent/duplicated"):
                cast_port.adapt_valve_workingset_refault("", tree)

    def test_unknown_sched_context_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'kernel/sched').mkdir(parents=True)
            (root / 'kernel/sched/core.c').write_text(VALVE_CORE.replace('donor, NULL', 'other, NULL'))
            source = root / 'cast.patch'
            output = root / 'cast-prepared.patch'
            source.write_text(UPSTREAM_PATCH)

            with self.assertRaisesRegex(RuntimeError, 'reviewed kernel API port'):
                cast_port.prepare(source, output, root)


if __name__ == '__main__':
    unittest.main()
