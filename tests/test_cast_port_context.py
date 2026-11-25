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
