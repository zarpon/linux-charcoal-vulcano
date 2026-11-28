#!/usr/bin/env python3
"""Expose the maintained Gentoo firmware logging switch for Charcoal builds."""
from __future__ import annotations

import re
import sys
from pathlib import Path

SYMBOL = "GENTOO_PRINT_FIRMWARE_INFO"
ANCHOR = "if FW_LOADER\n\n"
KCONFIG = '''config GENTOO_PRINT_FIRMWARE_INFO
	bool "Log requested firmware filenames"
	help
	  Print the filename of each firmware request using the maintained
	  Gentoo firmware information patch.

'''


def configure(tree: Path) -> None:
    source = (tree / "drivers/base/firmware_loader/main.c").read_text()
    guard = re.compile(
        r'#ifdef CONFIG_GENTOO_PRINT_FIRMWARE_INFO\n'
        r'[ \t]+printk\(KERN_NOTICE "Loading firmware: %s\\n", name\);\n'
        r'#endif'
    )
    if len(guard.findall(source)) != 1:
        raise ValueError("maintained Gentoo firmware logging patch must be applied first")
    path = tree / "drivers/base/firmware_loader/Kconfig"
    text = path.read_text()
    if re.search(rf"^config {SYMBOL}$", text, re.M):
        if text.count(KCONFIG) != 1:
            raise ValueError("unexpected existing firmware logging configuration")
        return
    if text.count(ANCHOR) != 1:
        raise ValueError("firmware loader Kconfig anchor changed")
    path.write_text(text.replace(ANCHOR, ANCHOR + KCONFIG, 1))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: configure-firmware-info.py <kernel-tree>")
    try:
        configure(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Firmware logging configuration: {exc}") from exc

