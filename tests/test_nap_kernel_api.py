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


    def test_preserves_version_guarded_upstream_060_irq_paths(self) -> None:
        original = (
            "        *loc = this_cpu_read(irq_stat.apic_timer_irqs);\\n"
            "        *res = this_cpu_read(irq_stat.irq_resched_count);\\n"
            "        *cal = this_cpu_read(irq_stat.irq_call_count);\\n"
        ).replace("\\n", "\n")
        guarded = (
            "#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)\n"
            "        *loc = this_cpu_read(irq_stat.counts[IRQ_COUNT_APIC_TIMER]);\n"
            "#ifdef CONFIG_SMP\n"
            "        *res = this_cpu_read(irq_stat.counts[IRQ_COUNT_RESCHEDULE]);\n"
            "        *cal = this_cpu_read(irq_stat.counts[IRQ_COUNT_CALL_FUNCTION]);\n"
            "#else\n"
            "        *res = *cal = 0;\n"
            "#endif\n"
            "#else\n"
            + original
            + "#endif\n"
        )
        assert original in FIXTURE
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nap.c"
            source.write_text(FIXTURE.replace(original, guarded), encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            first = source.read_text(encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            self.assertEqual(first, source.read_text(encoding="utf-8"))
            self.assertIn(guarded, first)
            self.assertEqual(first.count("const struct bin_attribute *attr"), 2)

    def test_dual_counters_without_version_guard_fail_closed(self) -> None:
        duplicate = FIXTURE.replace(
            "        *loc = this_cpu_read(irq_stat.apic_timer_irqs);",
            "        *loc = this_cpu_read(irq_stat.counts[IRQ_COUNT_APIC_TIMER]);\\n"
            "        *loc = this_cpu_read(irq_stat.apic_timer_irqs);".replace("\\n", "\n"),
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nap.c"
            source.write_text(duplicate, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source)], capture_output=True
            )
        self.assertNotEqual(result.returncode, 0)


    def test_accepts_nap_060_version_guarded_sysfs_contract(self) -> None:
        guarded = (
            "#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 16, 0)\n"
            "#define NAP_BIN_ATTR_CONST const\n"
            "#else\n"
            "#define NAP_BIN_ATTR_CONST\n"
            "#endif\n"
            + FIXTURE.replace(
                "struct bin_attribute *attr, char *buf,",
                "NAP_BIN_ATTR_CONST struct bin_attribute *attr,\n                            char *buf,",
            ).replace(
                "static struct bin_attribute *nap_bin_attrs[] = {",
                "static NAP_BIN_ATTR_CONST struct bin_attribute *\n"
                "NAP_BIN_ATTR_CONST nap_bin_attrs[] = {",
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nap.c"
            source.write_text(guarded, encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            first = source.read_text(encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            self.assertEqual(first, source.read_text(encoding="utf-8"))
            self.assertIn("NAP_BIN_ATTR_CONST nap_bin_attrs[] = {", first)
            self.assertEqual(first.count("NAP_BIN_ATTR_CONST struct bin_attribute *attr,"), 2)
            source.write_text(
                guarded.replace("#define NAP_BIN_ATTR_CONST const", "#define NAP_BIN_ATTR_CONST invalid"),
                encoding="utf-8",
            )
            result = subprocess.run([sys.executable, str(SCRIPT), str(source)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)



    def test_accepts_nap_065_compact_irq_and_sysfs_contract(self) -> None:
        upstream = (
            '#define CPUIDLE_NAP_VERSION "0.6.5"\n'
            "static void nap_irq_counts(u32 *dev, u32 *loc)\n"
            "{\n"
            "\t*dev = (u32)this_cpu_read(kstat.irqs_sum);\n"
            "#ifdef CONFIG_X86\n"
            "#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)\n"
            "\t/* 7.2 folded the per-class irq_stat fields into counts[] */\n"
            "\t*loc = this_cpu_read(irq_stat.counts[IRQ_COUNT_APIC_TIMER]);\n"
            "#else\n"
            "\t*loc = this_cpu_read(irq_stat.apic_timer_irqs);\n"
            "#endif\n"
            "#else\n\t*loc = 0;\n#endif\n}\n"
            "#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 16, 0)\n"
            "#define NAP_BIN_ATTR_CONST const\n"
            "#else\n#define NAP_BIN_ATTR_CONST\n#endif\n"
            "static ssize_t weights_read(struct file *file, struct kobject *kobj,\n"
            "\tNAP_BIN_ATTR_CONST struct bin_attribute *attr,\n"
            "\tchar *buf) { }\n"
            "static ssize_t weights_write(struct file *file, struct kobject *kobj,\n"
            "\tNAP_BIN_ATTR_CONST struct bin_attribute *attr,\n"
            "\tchar *buf) { }\n"
            "static NAP_BIN_ATTR_CONST struct bin_attribute *\n"
            "NAP_BIN_ATTR_CONST nap_bin_attrs[] = { NULL };\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nap.c"
            source.write_text(upstream, encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            self.assertEqual(source.read_text(encoding="utf-8"), upstream)
            subprocess.run([sys.executable, str(SCRIPT), str(source)], check=True)
            self.assertEqual(source.read_text(encoding="utf-8"), upstream)
            # A missing version guard must not silently pass as a native port.
            source.write_text(
                upstream.replace(
                    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)",
                    "#if 1",
                ),
                encoding="utf-8",
            )
            invalid = subprocess.run(
                [sys.executable, str(SCRIPT), str(source)], capture_output=True
            )
            self.assertNotEqual(invalid.returncode, 0)



if __name__ == "__main__":
    unittest.main()
