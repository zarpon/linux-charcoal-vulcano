#!/usr/bin/env python3
"""Regression for the exact BORE/ADIOS scripts/setlocalversion overlap."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "adios_scm_overlap", ROOT / "automation/port-adios-7.2.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SCM_PATCH = (
    MODULE.SCM_DIFF
    + "index 28169d7e14..5cb02894ac 100755\n"
    + "--- a/scripts/setlocalversion\n"
    + "+++ b/scripts/setlocalversion\n"
    + MODULE.SCM_HUNK
)
ELEVATOR_SOURCE = (
    "void elevator_set_default(struct request_queue *q)\n"
    "{\n"
    "\t\t.name = \"mq-deadline\",\n"
    "\tif ((q->nr_hw_queues == 1 ||\n"
    "\t\t\tblk_mq_is_shared_tags(q->tag_set->flags))) {\n"
    "\t}\n"
    "}\n"
)
UPSTREAM_ELEVATOR = (
    MODULE.ELEVATOR_DIFF
    + "--- a/block/elevator.c\n"
    + "+++ b/block/elevator.c\n"
    + "@@ -1,3 +1,6 @@\n"
    + " void elevator_set_default(struct request_queue *q)\n"
    + " {\n"
    + "+#ifdef CONFIG_MQ_IOSCHED_DEFAULT_ADIOS\n"
    + "+\tctx.name = \"adios\";\n"
    + "+#endif\n"
    + " }\n"
)
UPSTREAM = UPSTREAM_ELEVATOR + SCM_PATCH + "-- \n2.34.1\n"


class AdiosBoreOverlapTests(unittest.TestCase):
    def test_exact_duplicate_is_removed_without_dropping_elevator_changes(self):
        adapted = MODULE.adapt_patch(UPSTREAM, ELEVATOR_SOURCE, MODULE.SCM_APPLIED)
        self.assertNotIn(MODULE.SCM_DIFF, adapted)
        self.assertIn("CONFIG_MQ_IOSCHED_DEFAULT_ADIOS", adapted)
        self.assertIn("ctx.name", UPSTREAM)
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp)
            (tree / "block").mkdir()
            (tree / "scripts").mkdir()
            (tree / "block/elevator.c").write_text(ELEVATOR_SOURCE)
            (tree / "scripts/setlocalversion").write_text(MODULE.SCM_APPLIED)
            patch_path = tree / "adapted.patch"
            patch_path.write_text(adapted)
            subprocess.run(["git", "apply", "--check", str(patch_path)],
                           cwd=tree, check=True)
            subprocess.run(["git", "apply", str(patch_path)],
                           cwd=tree, check=True)
            self.assertEqual(
                (tree / "scripts/setlocalversion").read_text(),
                MODULE.SCM_APPLIED
            )
            self.assertIn(
                '.name = "adios"',
                (tree / "block/elevator.c").read_text()
            )

    def test_unpatched_scm_source_fails_closed(self):
        source = MODULE.SCM_APPLIED.replace("#echo", "echo")
        with self.assertRaisesRegex(MODULE.PortError, "not already applied"):
            MODULE.adapt_patch(UPSTREAM, ELEVATOR_SOURCE, source)

    def test_changed_upstream_scm_hunk_fails_closed(self):
        changed = UPSTREAM.replace("\t\t\t#echo", "\t\t\t##echo")
        with self.assertRaisesRegex(MODULE.PortError, "unreviewed"):
            MODULE.adapt_patch(changed, ELEVATOR_SOURCE, MODULE.SCM_APPLIED)

    def test_additional_unreviewed_scm_hunk_fails_closed(self):
        changed = UPSTREAM.replace(
            MODULE.SCM_HUNK,
            MODULE.SCM_HUNK + "@@ -1 +1 @@\n-old\n+new\n"
        )
        with self.assertRaisesRegex(MODULE.PortError, "unreviewed"):
            MODULE.adapt_patch(changed, ELEVATOR_SOURCE, MODULE.SCM_APPLIED)

    def test_unrelated_adios_hunks_remain_unchanged(self):
        adapted = MODULE.adapt_patch(UPSTREAM, ELEVATOR_SOURCE, MODULE.SCM_APPLIED)
        self.assertIn("diff --git a/block/elevator.c b/block/elevator.c", adapted)
        self.assertNotIn("diff --git a/scripts/setlocalversion", adapted)
        self.assertTrue(adapted.endswith("-- \n2.34.1\n"))


if __name__ == "__main__":
    unittest.main()
