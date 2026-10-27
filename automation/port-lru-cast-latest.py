#!/usr/bin/env python3
"""Prepare current CAST bytes, trying the unmodified patch before any port.

Only reviewed context differences are adapted. Unknown API changes fail
git apply --check and require a reviewed port; no older release or partially
applied kernel tree is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path


def check(tree: Path, patch: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', '-C', str(tree), 'apply', '--check', str(patch.resolve())],
                          text=True, capture_output=True)


def adapt_reviewed_contexts(patch: str, tree: Path) -> tuple[str, list[str]]:
    sections = re.split(r'(?=^diff --git )', patch, flags=re.M)
    adaptations: list[str] = []

    folio_path = tree / 'mm/folio.c'
    folio = folio_path.read_text(encoding='utf-8') if folio_path.is_file() else ''
    folio_anchor = ' #include <linux/buffer_head.h>\n'
    folio_added = '+#include <linux/lru_cast.h>\n'
    folio_old = folio_anchor + folio_added
    folio_new = folio_anchor + ' #include <linux/kvm_types.h>\n' + folio_added

    sched_path = tree / 'kernel/sched/core.c'
    sched = sched_path.read_text(encoding='utf-8') if sched_path.is_file() else ''
    sched_old = (' \tpsi_account_irqtime(rq, curr, NULL);\n'
                 '+\t/* a task that runs on without switching still sets young bits */\n'
                 '+\tlru_cast_use_mm(rq->curr->mm);\n')
    sched_new = (' \tpsi_account_irqtime(rq, donor, NULL);\n'
                 '+\t/* a task that runs on without switching still sets young bits */\n'
                 '+\tlru_cast_use_mm(rq->curr->mm);\n')

    for index, section in enumerate(sections):
        if section.startswith('diff --git a/mm/folio.c b/mm/folio.c\n'):
            if '#include <linux/kvm_types.h>' in folio and section.count(folio_old) == 1:
                sections[index] = section.replace(folio_old, folio_new, 1)
                adaptations.append('folio-kvm-types-include')
            elif '#include <linux/kvm_types.h>' not in folio and section.count(folio_new) == 1:
                sections[index] = section.replace(folio_new, folio_old, 1)
                adaptations.append('folio-without-kvm-types-include')
        elif section.startswith('diff --git a/kernel/sched/core.c b/kernel/sched/core.c\n'):
            if 'psi_account_irqtime(rq, donor, NULL);' in sched and section.count(sched_old) == 1:
                sections[index] = section.replace(sched_old, sched_new, 1)
                adaptations.append('valve-sched-tick-donor-context')

    return ''.join(sections), adaptations


def prepare(source: Path, output: Path, tree: Path) -> str:
    data = source.read_bytes()
    output.write_bytes(data)
    direct = check(tree, output)
    if direct.returncode == 0:
        return 'upstream-unmodified'

    adapted, adaptations = adapt_reviewed_contexts(data.decode('utf-8'), tree)
    if adaptations:
        output.write_text(adapted, encoding='utf-8', newline='\n')
        result = subprocess.run(['git', '-C', str(tree), 'apply', '--recount', '--check', str(output.resolve())],
                                text=True, capture_output=True)
        if result.returncode == 0:
            return 'ported-' + '+'.join(adaptations)
        detail = result.stderr
    else:
        detail = direct.stderr
    output.unlink()
    raise RuntimeError('latest CAST requires a reviewed kernel API port; refusing older release: ' + detail)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('tree', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('output must differ from locked upstream source')
    result = prepare(args.source, args.output, args.tree)
    for path in (args.source, args.output):
        print(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}')
    print(f'CAST preparation: {result}')


if __name__ == '__main__':
    main()
