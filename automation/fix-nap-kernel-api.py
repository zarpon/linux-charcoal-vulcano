#!/usr/bin/env python3
"""Adapt the current upstream NAP source to post-7.2 kernel APIs."""
from __future__ import annotations

import re
import sys
from pathlib import Path


REWRITES = (
    (
        "this_cpu_read(irq_stat.apic_timer_irqs)",
        "this_cpu_read(irq_stat.counts[IRQ_COUNT_APIC_TIMER])",
        1,
        "APIC timer counter",
    ),
    (
        "this_cpu_read(irq_stat.irq_resched_count)",
        "this_cpu_read(irq_stat.counts[IRQ_COUNT_RESCHEDULE])",
        1,
        "reschedule counter",
    ),
    (
        "this_cpu_read(irq_stat.irq_call_count)",
        "this_cpu_read(irq_stat.counts[IRQ_COUNT_CALL_FUNCTION])",
        1,
        "call-function counter",
    ),
    (
        "struct bin_attribute *attr, char *buf,",
        "const struct bin_attribute *attr, char *buf,",
        2,
        "binary-attribute callback constness",
    ),
    (
        "static struct bin_attribute *nap_bin_attrs[] = {",
        "static const struct bin_attribute * const nap_bin_attrs[] = {",
        1,
        "binary-attribute group constness",
    ),
)


def native_sysfs_const_contract(text: str) -> bool:
    """Recognize upstream NAP 0.6.0's complete version-guarded sysfs API."""
    return (
        text.count("#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 16, 0)") == 1
        and text.count("#define NAP_BIN_ATTR_CONST const") == 1
        and text.count("#define NAP_BIN_ATTR_CONST\n") == 1
        and text.count("NAP_BIN_ATTR_CONST struct bin_attribute *attr,") == 2
        and text.count("NAP_BIN_ATTR_CONST nap_bin_attrs[] = {") == 1
    )


def rewrite(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    for old, new, expected, label in REWRITES:
        pattern = re.compile(r"(?<!const )" + re.escape(old))
        old_count = len(pattern.findall(text))
        new_count = text.count(new)
        if old_count == expected and new_count == 0:
            text = pattern.sub(new, text)
            changed = True
        elif old_count == 0 and new_count == expected:
            continue
        elif (
            label in {"APIC timer counter", "reschedule counter", "call-function counter"}
            and old_count == expected
            and new_count == expected
            and "#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)" in text
            and text.index(new) < text.index(old)
            and re.search(r"(?m)^#else\s*$", text[text.index(new):text.index(old)])
        ):
            # NAP 0.6.0 intentionally keeps pre-7.2 and 7.2+ IRQ branches.
            # Do not rewrite the legacy branch or weaken the fail-closed checks.
            continue
        elif (
            label in {"binary-attribute callback constness", "binary-attribute group constness"}
            and old_count == 0
            and new_count == 0
            and native_sysfs_const_contract(text)
        ):
            # Upstream NAP 0.6.0 already guards sysfs constness by kernel version.
            continue
        else:
            raise SystemExit(
                f"{label}: expected {expected} old or new anchors, "
                f"found old={old_count} new={new_count}"
            )
    path.write_text(text, encoding="utf-8")
    return changed


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: fix-nap-kernel-api.py <drivers/cpuidle/governors/nap/nap.c>")
    changed = rewrite(Path(sys.argv[1]))
    print(f"NAP kernel API compatibility changed={changed}")


if __name__ == "__main__":
    main()
