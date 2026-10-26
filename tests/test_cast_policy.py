import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('charcoal_cast_policy', ROOT / 'automation/resolve-latest-patches.py')
resolver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resolver
SPEC.loader.exec_module(resolver)


class CastPolicyTests(unittest.TestCase):
    def component(self):
        manifest = json.loads((ROOT / 'automation/patch-sources.json').read_text())
        return next(item for item in manifest['components'] if item['name'] == 'lru_cast')

    def test_current_upstream_layout_and_newest_native_selection(self):
        paths = ['patches/0001-7.2-rc1-lru_cast-v0.2.5.patch',
                 'patches/0001-7.3-rc7-lru_cast-v0.2.5.patch',
                 'patches/0001-7.2-rc1-lru_cast-v0.2.4.patch']
        tree = {'tree': [{'path': path, 'type': 'blob'} for path in paths]}
        with mock.patch.object(resolver, 'repository_tree', return_value=('a'*40, tree)):
            record = resolver.resolve_github_component(self.component(), '7.2.7', None, ROOT)
        self.assertEqual(record['path'], paths[0])
        self.assertEqual(record['project_version'], '0.2.5')
        self.assertEqual(record['origin'], 'upstream-native')

    def test_newer_foreign_revision_is_selected_for_port(self):
        paths = ['patches/0001-7.2-rc1-lru_cast-v0.2.5.patch',
                 'patches/0001-7.3-rc7-lru_cast-v0.2.5r2.patch']
        tree = {'tree': [{'path': path, 'type': 'blob'} for path in paths]}
        patch = b'diff --git a/test b/test\n--- a/test\n+++ b/test\n@@ -1 +1 @@\n-old\n+new\n'
        with mock.patch.object(resolver, 'repository_tree', return_value=('a'*40, tree)), \
             mock.patch.object(resolver, 'request_bytes', return_value=patch):
            record = resolver.resolve_github_component(self.component(), '7.2.7', None, ROOT)
        self.assertEqual(record['project_version'], '0.2.5r2')
        self.assertEqual(record['origin'], 'adaptive-port')
        self.assertEqual(record['selection'], 'latest-release-adaptive-port')
        self.assertEqual(record['path'], paths[1])
        self.assertEqual(record['latest_upstream_project_version'], '0.2.5r2')

    def test_default_configuration_and_no_swappiness_override(self):
        config = (ROOT / 'config-charcoal').read_text()
        pkgbuild = (ROOT / 'PKGBUILD').read_text()
        self.assertIn('CONFIG_LRU_CAST=y', config)
        self.assertNotIn('LRU_MARIE', config)
        self.assertIn("'CONFIG_LRU_CAST=y'", pkgbuild)
        self.assertIn('port-lru-cast-latest.py', pkgbuild)
        self.assertNotIn('swappiness', (ROOT / '99-charcoal-sysctl.conf').read_text())


if __name__ == '__main__':
    unittest.main()
