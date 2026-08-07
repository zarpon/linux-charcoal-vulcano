#!/usr/bin/env python3
"""Apply the locked Zen cpufreq schedutil removal to the Valve 7.2 layout."""
from __future__ import annotations

import argparse
from pathlib import Path

DIFF_HEADER = "diff --git a/drivers/cpufreq/Kconfig.x86 b/drivers/cpufreq/Kconfig.x86"
REMOVED = "-\tselect CPU_FREQ_GOV_SCHEDUTIL if SMP"
TARGET = "\tselect CPU_FREQ_GOV_SCHEDUTIL if SMP\n"
CONFIGS = ("X86_INTEL_PSTATE", "X86_AMD_PSTATE")


class PortError(RuntimeError):
    pass


def validate_patch(patch: str) -> None:
    if DIFF_HEADER not in patch:
        raise PortError("Zen patch no longer targets drivers/cpufreq/Kconfig.x86")
    if patch.count(REMOVED) != 2:
        raise PortError("Zen cpufreq patch no longer removes exactly two schedutil selects")
    for config in CONFIGS:
        if f"config {config}" not in patch:
            raise PortError(f"Zen cpufreq patch no longer contains {config}")


def config_bounds(source: str, config: str) -> tuple[int, int]:
    marker = f"config {config}\n"
    start = source.find(marker)
    if start < 0:
        raise PortError(f"Valve 7.2 target is missing {config}")
    next_config = source.find("\nconfig ", start + len(marker))
    end = len(source) if next_config < 0 else next_config + 1
    return start, end


def adapt_source(source: str) -> str:
    updated = source
    for config in CONFIGS:
        start, end = config_bounds(updated, config)
        block = updated[start:end]
        if block.count(TARGET) != 1:
            raise PortError(
                f"expected exactly one schedutil select inside {config}, "
                f"found {block.count(TARGET)}"
            )
        block = block.replace(TARGET, "", 1)
        updated = updated[:start] + block + updated[end:]
    if updated.count(TARGET) != 0:
        raise PortError("unexpected schedutil select remains outside the reviewed P-State stanzas")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patch", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        patch = args.patch.read_text(encoding="utf-8")
        source = args.target.read_text(encoding="utf-8")
        validate_patch(patch)
        adapted = adapt_source(source)
    except (OSError, UnicodeDecodeError, PortError) as exc:
        raise SystemExit(f"Zen cpufreq 7.2 port failed: {exc}") from exc
    args.target.write_text(adapted, encoding="utf-8")
    print(
        "Applied explicit Zen cab7ea1 cpufreq port for Valve 7.2: "
        "removed schedutil selects from Intel/AMD P-State"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
