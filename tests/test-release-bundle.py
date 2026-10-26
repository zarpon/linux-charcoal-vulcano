import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def test_actual_workflow_bundle_has_packages_audit_notes_and_matching_sha256(self):
        workflow = (ROOT / '.github/workflows/push.yml').read_text()
        source = workflow.split('          python3 - "$RELEASE_ZIP"', 1)[1]
        source = source.split("<<'PY'", 1)[1].split('\n          PY', 1)[0]
        source = '\n'.join(line[10:] if line.startswith(' ' * 10) else line for line in source.splitlines())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'logs').mkdir()
            audit = ('patch-lock.json', 'steamos-stable-source.json', 'checksum-validation.txt', 'release-notes.md', 'zstd-crypto-level.txt', 'zstd-crypto-source.sha256')
            for name in audit:
                (root / 'logs' / name).write_text('audit fixture\n')
            for name in ('README.md', 'README.pt-BR.md'):
                (root / name).write_text('documentation fixture\n')
            for part in ('', '-headers'):
                (root / f'linux-charcoal-73{part}-7.3.1.valve1.cc1-1-x86_64.pkg.tar.zst').write_bytes(b'package fixture')
            archive = root / 'linux-charcoal-73-7.3.1.valve1.cc1-r1.zip'
            subprocess.run([sys.executable, '-', archive.name], input=source, text=True, cwd=root,
                           env={**os.environ, 'PKGBASE': 'linux-charcoal-73'}, check=True)
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                names = z.namelist()
                self.assertEqual(len(names), len(set(names)))
                self.assertTrue(set(audit) <= set(names))
                self.assertIn('README.md', names)
                self.assertIn('README.pt-BR.md', names)
                self.assertFalse(any(name.endswith('.zip') for name in names))
                for line in z.read('SHA256SUMS').decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), digest)
            self.assertEqual((root / 'RELEASE-ZIP-SHA256SUM').read_text(), hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')


if __name__ == '__main__':
    unittest.main()
