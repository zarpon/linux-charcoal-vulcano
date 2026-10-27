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
