#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "automation/fix-nap-kernel-api.py"

FIXTURE = """static u32 nap_irq_total(u32 *dev, u32 *loc, u32 *res, u32 *cal)
{
        *loc = this_cpu_read(irq_stat.apic_timer_irqs);
        *res = this_cpu_read(irq_stat.irq_resched_count);
        *cal = this_cpu_read(irq_stat.irq_call_count);
}
static ssize_t weights_read(struct file *file, struct kobject *kobj,
                            struct bin_attribute *attr, char *buf,
                            loff_t off, size_t count) { }
static ssize_t weights_write(struct file *file, struct kobject *kobj,
                             struct bin_attribute *attr, char *buf,
                             loff_t off, size_t count) { }
static struct bin_attribute *nap_bin_attrs[] = {
        &bin_attr_weights,
        NULL,
};
"""


class NapKernelApiTests(unittest.TestCase):
    def test_ports_all_renamed_apis_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nap.c"
            source.write_text(FIXTURE, encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            first = source.read_text(encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            second = source.read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertIn("irq_stat.counts[IRQ_COUNT_APIC_TIMER]", first)
        self.assertIn("irq_stat.counts[IRQ_COUNT_RESCHEDULE]", first)
        self.assertIn("irq_stat.counts[IRQ_COUNT_CALL_FUNCTION]", first)
        self.assertEqual(first.count("const struct bin_attribute *attr"), 2)
        self.assertIn(
            "static const struct bin_attribute * const nap_bin_attrs[]", first
        )

    def test_fails_closed_on_partial_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nap.c"
            source.write_text(
                FIXTURE.replace(
                    "this_cpu_read(irq_stat.irq_call_count)", "unsupported_call_counter()"
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
