import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('stable_source', ROOT / 'automation/prepare-steamos-stable.py')
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def metadata(version='3.9.5', branch='stable'):
    return {'minor': {'candidates': [{'image': {'version': version, 'buildid': '20261023.100',
            'branch': branch, 'product': 'steamos', 'arch': 'amd64', 'variant': 'steamdeck'}}]}}


class StableTrackingTests(unittest.TestCase):
    def test_tracks_stable_os_and_kernel_series_changes_together(self):
        base = json.loads((ROOT / 'automation/patch-sources.json').read_text())
        policy = json.loads((ROOT / 'automation/patch-source-overrides-7.2.json').read_text())
        for os_version, kernel, suffix, repo in (
                ('3.9.5', '7.2.7', '72', 'jupiter-3.9'),
                ('3.10.1', '7.3.2', '73', 'jupiter-3.10'),
                ('4.0.0', '8.0.1', '80', 'jupiter-4.0')):
            with self.subTest(os=os_version, kernel=kernel):
                packages = f'linux-neptune-{suffix} {kernel}.valve2-2\nlinux-neptune-{suffix}-headers {kernel}.valve2-2\n'
                manifest, overrides, record = MODULE.prepare(metadata(os_version), packages, base, policy)
                series = '.'.join(kernel.split('.')[:2])
                self.assertEqual(manifest['kernel_source']['series'], series)
                self.assertEqual(manifest['kernel_source']['preferred_tag'], kernel + '-valve2')
                self.assertFalse(manifest['kernel_source']['allow_prerelease'])
                self.assertTrue(record['source_index'].endswith(repo + '/'))
                self.assertEqual(record['pkgbase'], 'linux-charcoal-' + suffix)
                self.assertTrue(record['package']['url'].endswith(f'linux-neptune-{suffix}-{kernel}.valve2-2.src.tar.gz'))
                self.assertEqual(overrides['components']['zram_ir']['port_for_kernel'], series)
                # No family or reviewed port may disappear during a series transition.
                self.assertEqual(set(overrides['components']), set(policy['components']))
                self.assertEqual(overrides['components']['zram_ir']['local_port'], policy['components']['zram_ir']['local_port'])

    def test_never_uses_preview_as_stable(self):
        for branch in ('main', 'beta', 'preview'):
            with self.assertRaisesRegex(ValueError, 'no SteamOS stable'):
                MODULE.stable_image(metadata(branch=branch))

    def test_prefers_numeric_os_version_not_lexical_order(self):
        data = metadata('3.9.5')
        data['major'] = metadata('3.10.1')['minor']
        self.assertEqual(MODULE.stable_image(data)['version'], '3.10.1')

    def test_rejects_untrusted_image_path_components(self):
        data = metadata()
        data['minor']['candidates'][0]['image']['buildid'] = '../preview'
        with self.assertRaises(ValueError):
            MODULE.stable_image(data)

    def test_requires_one_exact_release_kernel_in_image(self):
        for packages in ('', 'linux-neptune-73 7.2.7.valve2-2',
                         'linux-neptune-72 7.2.8.rc1.valve.beta1-1',
                         'linux-neptune-72 7.2.7.valve2-2\nlinux-neptune-73 7.3.1.valve1-1'):
            with self.subTest(packages=packages), self.assertRaises(ValueError):
                MODULE.kernel_package(packages)


if __name__ == '__main__':
    unittest.main()
