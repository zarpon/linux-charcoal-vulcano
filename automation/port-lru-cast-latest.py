#!/usr/bin/env python3
"""Prepare current CAST bytes, trying the unmodified patch before any port.

Only the reviewed mm/folio.c kvm_types.h include-context change is adapted.
Unknown API changes fail git apply --check and require a reviewed port; no
older release or partially applied kernel tree is accepted.
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


def prepare(source: Path, output: Path, tree: Path) -> str:
    data = source.read_bytes()
    output.write_bytes(data)
    direct = check(tree, output)
    if direct.returncode == 0:
        return 'upstream-unmodified'
    patch = data.decode('utf-8')
    folio_path = tree / 'mm/folio.c'
    folio = folio_path.read_text(encoding='utf-8') if folio_path.is_file() else ''
    # The 7.3 include was added beside buffer_head.h. Older CAST variants
    # have that exact include as the anchor immediately before CAST's include.
    anchor = ' #include <linux/buffer_head.h>\n'
    added = '+#include <linux/lru_cast.h>\n'
    old = anchor + added
    new = anchor + ' #include <linux/kvm_types.h>\n' + added
    sections = re.split(r'(?=^diff --git )', patch, flags=re.M)
    changed = False
    for index, section in enumerate(sections):
        if not section.startswith('diff --git a/mm/folio.c b/mm/folio.c\n'):
            continue
        if '#include <linux/kvm_types.h>' in folio and section.count(old) == 1:
            sections[index] = section.replace(old, new, 1)
            changed = True
        elif '#include <linux/kvm_types.h>' not in folio and section.count(new) == 1:
            sections[index] = section.replace(new, old, 1)
            changed = True
    if changed:
        # Context changed by one line; --recount recalculates hunk lengths.
        output.write_text(''.join(sections), encoding='utf-8', newline='\n')
        result = subprocess.run(['git', '-C', str(tree), 'apply', '--recount', '--check', str(output.resolve())],
                                text=True, capture_output=True)
        if result.returncode == 0:
            return 'ported-folio-include-context'
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
