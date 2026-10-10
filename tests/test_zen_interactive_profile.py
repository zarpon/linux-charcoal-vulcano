from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'zen_two_patch_profile', ROOT / 'automation/configure-zen-interactive.py'
)
assert SPEC and SPEC.loader
ZEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ZEN)


class ZenProfileTests(unittest.TestCase):
    def fixture(self, tree: Path) -> None:
        files = {
            'init/Kconfig': 'config BROKEN\n\tbool\n',
            'drivers/input/evdev.c': (
                'static void evdev_reclaim_client(struct rcu_head *rp) {}\n'
                'static void evdev_detach_client(void) {\n'
                '\tcall_rcu(&client->rcu, evdev_reclaim_client);\n}\n'
            ),
            'drivers/cpufreq/Kconfig.x86': (
                'config X86_INTEL_PSTATE\n\tselect ACPI_PROCESSOR\n\thelp\n\t  Intel\n'
                'config X86_AMD_PSTATE\n\tselect ACPI_CPPC_LIB\n\thelp\n\t  AMD\n'
            ),
            'mm/lru_marie/core.c': 'Marie own defaults must remain untouched\n',
        }
        for name, text in files.items():
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def test_gates_both_existing_patches_without_changing_marie(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.fixture(tree)
            before = (tree / 'mm/lru_marie/core.c').read_bytes()
            ZEN.configure(tree)
            first = {str(p.relative_to(tree)): p.read_bytes() for p in tree.rglob('*') if p.is_file()}
            ZEN.configure(tree)
            self.assertEqual(first, {str(p.relative_to(tree)): p.read_bytes() for p in tree.rglob('*') if p.is_file()})
            self.assertEqual(before, (tree / 'mm/lru_marie/core.c').read_bytes())
            source = (tree / 'drivers/input/evdev.c').read_text()
            self.assertIn('IS_ENABLED(CONFIG_ZEN_INTERACTIVE)', source)
            self.assertIn('synchronize_rcu();', source)
            self.assertIn('evdev_reclaim_client(&client->rcu);', source)
            self.assertEqual((tree / 'drivers/cpufreq/Kconfig.x86').read_text().count('if SMP && !ZEN_INTERACTIVE'), 2)

    def test_missing_upstream_patch_fails_before_writing_any_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.fixture(tree)
            (tree / 'drivers/input/evdev.c').write_text('original evdev without the patch\n')
            before = {str(p.relative_to(tree)): p.read_bytes() for p in tree.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError, 'evdev patch must be applied first'):
                ZEN.configure(tree)
            self.assertEqual(before, {str(p.relative_to(tree)): p.read_bytes() for p in tree.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
