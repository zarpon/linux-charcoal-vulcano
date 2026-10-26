import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'zstd-crypto-default-level-1.patch'
SOURCE = ('/* header */\n' * 16 + '#include <crypto/scatterwalk.h>\n\n\n'
          '#define ZSTD_DEF_LEVEL\t\t3\n#define ZSTD_MAX_WINDOWLOG\t18\n'
          '#define ZSTD_MAX_SIZE\t\tBIT(ZSTD_MAX_WINDOWLOG)\n\n'
          'params = zstd_get_params(ZSTD_DEF_LEVEL, ZSTD_MAX_SIZE);\n'
          'wksp_size = zstd_cstream_workspace_bound(&params.cParams);\n')


class ZstdDefaultTests(unittest.TestCase):
    def apply_patch(self, source):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'crypto/zstd.c'
            target.parent.mkdir()
            target.write_text(source)
            result = subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-Np1', '-i', str(PATCH)],
                                    cwd=directory, text=True, capture_output=True)
            return result, target.read_text()

    def test_changes_only_the_generic_default_and_keeps_parameter_allocation(self):
        result, output = self.apply_patch(SOURCE)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(output, SOURCE.replace('ZSTD_DEF_LEVEL\t\t3', 'ZSTD_DEF_LEVEL\t\t1'))
        self.assertIn('zstd_get_params(ZSTD_DEF_LEVEL, ZSTD_MAX_SIZE)', output)
        self.assertIn('zstd_cstream_workspace_bound(&params.cParams)', output)

    def test_rejects_upstream_default_drift_without_silent_override(self):
        changed = SOURCE.replace('ZSTD_DEF_LEVEL\t\t3', 'ZSTD_DEF_LEVEL\t\t5')
        result, output = self.apply_patch(changed)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, changed)

    def test_recipe_carries_patch_checksum_and_checks_the_prepared_source(self):
        text = (ROOT / 'PKGBUILD').read_text()
        self.assertIn(PATCH.name, text)
        self.assertIn(hashlib.sha256(PATCH.read_bytes()).hexdigest(), text)
        self.assertIn('ZSTD_DEF_LEVEL[[:space:]]+1', text)
        self.assertIn('logs/zstd-crypto-level.txt', text)
        self.assertIn('_ver=2', text)
        self.assertIn('sha256sum crypto/zstd.c', text)


if __name__ == '__main__':
    unittest.main()
