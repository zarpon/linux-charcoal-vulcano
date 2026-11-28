import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / 'install-charcoal.sh').read_text()


def embedded(function):
    body = INSTALLER.split(function + '() {', 1)[1].split("<<'PY'", 1)[1].split('\nPY', 1)[0]
    return body.lstrip('\n')


class IntegrityTests(unittest.TestCase):
    def run_extract(self, members, checksums=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            archive = path / 'release.zip'
            if checksums is None:
                checksums = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in members.items())
            with zipfile.ZipFile(archive, 'w') as z:
                for name, data in members.items():
                    z.writestr(name, data)
                z.writestr('SHA256SUMS', checksums)
            return subprocess.run([sys.executable, '-', str(archive), str(path / 'packages')],
                                  input=embedded('extract_and_verify_packages'), text=True, capture_output=True)

    @staticmethod
    def pair(suffix='72'):
        return {f'linux-charcoal-{suffix}-7.2.7.valve2.cc1-1-x86_64.pkg.tar.zst': b'kernel',
                f'linux-charcoal-{suffix}-headers-7.2.7.valve2.cc1-1-x86_64.pkg.tar.zst': b'headers'}

    def test_extracts_matching_pair_across_future_kernel_series(self):
        for suffix in ('72', '73', '80'):
            result = self.run_extract(self.pair(suffix))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_corrupted_package_and_mixed_series(self):
        result = self.run_extract(self.pair(), '0' * 64 + '  ignored\n')
        self.assertNotEqual(result.returncode, 0)
        members = self.pair()
        headers = next(name for name in members if '-headers-' in name)
        members[headers.replace('-72-', '-73-')] = members.pop(headers)
        result = self.run_extract(members)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('different series', result.stderr)

    def test_rejects_path_traversal_in_place_of_headers(self):
        members = self.pair()
        headers = next(name for name in members if '-headers-' in name)
        members['../' + headers] = members.pop(headers)
        self.assertNotEqual(self.run_extract(members).returncode, 0)

    def test_notes_follow_actual_lock_kernel_version(self):
        spec = importlib.util.spec_from_file_location('release_notes', ROOT / 'automation/generate-release-notes.py')
        notes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(notes)
        for kernel in ('7.2.7', '7.3.1', '8.0.1'):
            tag = kernel + '-valve2'
            version = kernel + '.valve2.cc1'
            lock = {'kernel': {'version': kernel, 'tag': tag}, 'components': {'bore': {'sha256': 'a' * 64, 'project_version': '6.9.0'}}}
            result = notes.render('stable', lock, version, tag, 'kernel.zip', 'charcoal-' + version + '-r1', 'abc', '1')
            self.assertIn(kernel, result)
            self.assertIn('Latest', result)
            with self.assertRaises(ValueError):
                notes.render('stable', lock, version, tag, 'kernel.zip', 'charcoal-6.18.1-r1', 'abc', '1')


    def test_notes_show_local_port_upstream_version_and_hash(self):
        spec = importlib.util.spec_from_file_location('release_notes', ROOT / 'automation/generate-release-notes.py')
        notes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(notes)
        components = {'zram_ir': {
            'origin': 'local-port', 'selection': 'latest-release-port',
            'path': '0001-linux7.2-zram-ir-1.2.patch', 'commit': 'repository-local',
            'sha256': 'a' * 64,
            'upstream': {
                'repository': 'firelzrd/zram-ir', 'project_version': '1.3',
                'latest_upstream_project_version': '1.3', 'kernel_version': '7.3',
                'path': 'patches/0001-linux7.3-rc1-zram-ir-1.3.patch',
                'commit': 'b' * 40, 'sha256': 'c' * 64,
            },
        }}
        result = '\n'.join(notes.format_components(components))
        self.assertIn('| **ZRAM-IR** | `1.3` | `7.3` | latest-release-port |', result)
        self.assertNotIn('não registrada', result)
        self.assertNotIn('Commit upstream: `repository-local`', result)
        self.assertIn('SHA256 original antes do porte: `' + 'c' * 64 + '`', result)
        self.assertIn('Revisão global mais recente: `1.3`', result)


if __name__ == '__main__':
    unittest.main()
