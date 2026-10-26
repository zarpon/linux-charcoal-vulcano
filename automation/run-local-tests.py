#!/usr/bin/env python3
"""Run every regression file, including hyphenated names skipped by discovery."""
from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    for folder in ('automation', 'tests', 'nap-tools'):
        for path in (ROOT / folder).rglob('*.py'):
            py_compile.compile(str(path), doraise=True)
    for path in [ROOT / 'PKGBUILD', ROOT / 'install-charcoal.sh', ROOT / 'configure-zram-ir', ROOT / 'docker/setup.sh']:
        subprocess.run(['bash', '-n', str(path)], cwd=ROOT, check=True)
    files = sorted((ROOT / 'tests').glob('test*.py'))
    for path in files:
        print(f'Running {path.name}', flush=True)
        subprocess.run([sys.executable, str(path), '-v'], cwd=ROOT, check=True)
    for path in sorted((ROOT / 'tests').glob('test*.sh')):
        subprocess.run(['bash', str(path)], cwd=ROOT, check=True)
    print(f'Passed all {len(files)} Python regression files and shell suites', flush=True)


if __name__ == '__main__':
    main()
