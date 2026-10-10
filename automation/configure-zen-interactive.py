#!/usr/bin/env python3
"""Expose and gate only the two existing Zen patches after their application."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ZEN_KCONFIG = '''config ZEN_INTERACTIVE
	bool "Zen interactive input and P-State tuning"
	help
	  Use asynchronous RCU reclamation when detaching evdev clients and
	  remove the Intel/AMD P-State drivers' forced schedutil selection.
	  This profile contains only those two existing Zen patches. It does
	  not change scheduler, reclaim, compaction, THP or swap defaults.

'''

RCU_OLD = '\tcall_rcu(&client->rcu, evdev_reclaim_client);'
RCU_NEW = '''	if (IS_ENABLED(CONFIG_ZEN_INTERACTIVE)) {
		call_rcu(&client->rcu, evdev_reclaim_client);
	} else {
		synchronize_rcu();
		evdev_reclaim_client(&client->rcu);
	}'''
PSTATE_SELECT = '\tselect CPU_FREQ_GOV_SCHEDUTIL if SMP && !ZEN_INTERACTIVE\n'


def configure(tree: Path) -> None:
    kconfig = tree / 'init/Kconfig'
    evdev = tree / 'drivers/input/evdev.c'
    pstate = tree / 'drivers/cpufreq/Kconfig.x86'
    ktext, etext, ptext = [p.read_text() for p in (kconfig, evdev, pstate)]

    # Validate every anchor before writing any file. Unexpected upstream
    # implementations must be reviewed rather than silently mixed together.
    if re.search(r'^config ZEN_INTERACTIVE$', ktext, re.M):
        if ZEN_KCONFIG not in ktext:
            raise ValueError('Unexpected pre-existing ZEN_INTERACTIVE profile')
    else:
        if ktext.count('config BROKEN\n') != 1:
            raise ValueError('init/Kconfig BROKEN anchor changed')
        ktext = ktext.replace('config BROKEN\n', ZEN_KCONFIG + 'config BROKEN\n', 1)

    if RCU_NEW not in etext:
        if etext.count(RCU_OLD) != 1 or 'static void evdev_reclaim_client(' not in etext:
            raise ValueError('The existing Zen evdev patch must be applied first')
        etext = etext.replace(RCU_OLD, RCU_NEW, 1)

    for symbol in ('X86_INTEL_PSTATE', 'X86_AMD_PSTATE'):
        pattern = re.compile(rf'(^config {symbol}\n)(.*?)(?=^config |\Z)', re.M | re.S)
        match = pattern.search(ptext)
        if not match:
            raise ValueError(f'{symbol} Kconfig block missing')
        block = match[0]
        if PSTATE_SELECT not in block:
            if 'select CPU_FREQ_GOV_SCHEDUTIL' in block or block.count('\thelp\n') != 1:
                raise ValueError(f'The existing Zen P-State patch must be applied first: {symbol}')
            block = block.replace('\thelp\n', PSTATE_SELECT + '\thelp\n', 1)
            ptext = ptext[:match.start()] + block + ptext[match.end():]

    for path, text in ((kconfig, ktext), (evdev, etext), (pstate, ptext)):
        path.write_text(text)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: configure-zen-interactive.py <kernel-tree>')
    try:
        configure(Path(sys.argv[1]))
    except ValueError as exc:
        raise SystemExit(f'Zen two-patch profile: {exc}')
