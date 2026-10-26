#!/usr/bin/env python3
"""Protect BORE family coverage and the retained compatibility reference."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'automation/patch-sources.json').read_text())
components = {item['name']: item for item in manifest['components']}
for name, target in (('bore', 'latest-bore.patch'), ('bore_sched_ext_coexistence', 'latest-bore-sched-ext-coexistence-fix.patch')):
    spec = components[name]
    assert spec['target'] == target
    assert spec['always_latest'] is True
    assert not spec.get('local_port'), 'obsolete 6.18 port must not shadow current upstream'
    assert target in (root / 'PKGBUILD').read_text()
reference = root / '6.16.12-bore-6.8.0-final.patch'
subprocess.run(['git', 'apply', '--numstat', str(reference)], cwd=root, check=True, capture_output=True)
print('BORE and sched_ext family coverage and retained overlay syntax passed')
