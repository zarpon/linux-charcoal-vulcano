#!/usr/bin/env python3
"""Exercise migration failures in a temporary root; never touch host swap."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packaging/configure-gaming-swap"
if not SCRIPT.exists():
    SCRIPT = ROOT / "configure-gaming-swap"
loader = importlib.machinery.SourceFileLoader("gaming_swap", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
policy = importlib.util.module_from_spec(spec)
loader.exec_module(policy)


class FakeMigration(policy.Migration):
    def __init__(self, root):
        super().__init__(root)
        self.calls = []
        self.swaps = {"/home/swapfile": "file", "/dev/zram0": "partition", "/dev/sda3": "partition"}
        self.filesystem = "ext4"
        self.fail_command = None
        self.unit_names = {"steamos-zram-swap.service", "systemd-zram-setup@zram0.service", "dev-zram0.swap", "home-swapfile.swap"}
        for directory in ("/proc", "/home", "/etc/default", "/sys/module/zswap/parameters"):
            self.path(directory).mkdir(parents=True, exist_ok=True)
        self.path("/proc/meminfo").write_text("MemTotal:        8192 kB\n")
        self.make_swap("/home/swapfile", 1024**2)
        self.path("/etc/fstab").write_text("# user's mounts\nUUID=home /home ext4 defaults 0 2\n/home/swapfile none swap sw 0 0\n/dev/zram0 none swap defaults 0 0\n/dev/sda3 none swap defaults 0 0\n")
        self.path("/etc/default/grub").write_text('GRUB_CMDLINE_LINUX="quiet module_blacklist=bad_driver zswap.enabled=0"\nGRUB_CMDLINE_LINUX_DEFAULT="systemd.zram=1 splash"\n')
        for key, value in policy.PARAMETERS.items():
            if key != "zpool":
                self.path("/sys/module/zswap/parameters/" + key).write_text(value)

    def make_swap(self, name, size):
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:
            f.write(b"SWAP")
            f.truncate(size)

    def logical(self, path):
        return path[len(str(self.root)):] if path.startswith(str(self.root)) else path

    def run(self, *args, check=True):
        self.calls.append(args)
        if self.fail_command and self.fail_command(args):
            if check:
                raise subprocess.CalledProcessError(1, args, stderr="injected failure")
            return subprocess.CompletedProcess(args, 1, "", "injected failure")
        output = ""
        status = 0
        if args[:2] == ("swapon", "--show"):
            output = json.dumps({"swapdevices": [{"name": k, "type": v} for k, v in self.swaps.items()]})
        elif args[0] == "swapon":
            self.swaps[self.logical(args[1])] = "file"
        elif args[0] == "swapoff":
            self.swaps.pop(self.logical(args[1]), None)
        elif args[0] == "blkid":
            with Path(args[-1]).open("rb") as f:
                if f.read(4) == b"SWAP":
                    output = "swap\n"
                else:
                    status = 2
        elif args[0] == "findmnt":
            output = self.filesystem + "\n"
        elif args[0] == "dd":
            opts = dict(v.split("=", 1) for v in args[1:])
            with Path(opts["of"]).open("wb") as f:
                f.truncate(int(opts["count"]))
        elif args[0] == "mkswap":
            with Path(args[1]).open("r+b") as f:
                f.write(b"SWAP")
        elif args[:3] == ("btrfs", "subvolume", "create"):
            Path(args[-1]).mkdir()
        elif args[:3] == ("btrfs", "filesystem", "mkswapfile"):
            self.make_swap(self.logical(args[-1]), int(args[-2]))
        elif args[:2] in {("systemctl", "list-unit-files"), ("systemctl", "list-units")}:
            output = "\n".join(name + " enabled" for name in self.unit_names)
        elif args[:2] == ("systemctl", "show"):
            output = "/home/swapfile\n" if args[-1] == "home-swapfile.swap" else ""
        return subprocess.CompletedProcess(args, status, output, "")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.m = FakeMigration(Path(self.temp.name))
        self.which = patch.object(policy.shutil, "which", return_value="/fake/command")
        self.which.start()
        self.addCleanup(self.which.stop)

    def install(self):
        with patch.object(policy.shutil, "disk_usage", return_value=type("Disk", (), {"free": 10 * 1024**3})()):
            self.m.install()

    def test_replacement_active_before_drain_and_persistent_after_boot(self):
        self.install()
        target = "/home/.gaming-swap/swapfile"
        self.assertEqual(self.m.path(target).stat().st_size, 8192 * 1024 * 3 // 2)
        self.assertEqual(self.m.path(target).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.m.path("/home/.gaming-swap").stat().st_mode & 0o777, 0o700)
        calls = self.m.calls
        activate = next(i for i, c in enumerate(calls) if c[0] == "swapon" and c[1] != "--show")
        drain = next(i for i, c in enumerate(calls) if c[0] == "swapoff")
        self.assertLess(activate, drain)
        self.assertFalse(self.m.path("/home/swapfile").exists())
        self.assertIn("/dev/sda3", self.m.swaps)
        self.assertNotIn("/dev/zram0", self.m.swaps)
        for unit in ("steamos-zram-swap.service", "systemd-zram-setup@.service", "home-swapfile.swap"):
            self.assertEqual(self.m.path("/etc/systemd/system/" + unit).readlink(), Path("/dev/null"))
        fstab = self.m.path("/etc/fstab").read_text()
        self.assertIn("/dev/sda3 none swap", fstab)
        self.assertNotIn("/home/swapfile none", fstab)
        self.assertNotIn("/dev/zram0", fstab)
        self.assertIn(target + " none swap", fstab)
        self.assertIn("x-systemd.after=gaming-zswap.service", fstab)
        self.assertIn(("systemctl", "enable", "gaming-zswap.service"), calls)
        self.assertIn("install zram /bin/false", self.m.path("/etc/modprobe.d/99-gaming-swap.conf").read_text())
        self.assertIn("zram-size = 0", self.m.path("/etc/systemd/zram-generator.conf.d/99-gaming-swap.conf").read_text())

    def test_updates_are_idempotent(self):
        self.install()
        original = self.m.path("/etc/fstab").read_text()
        self.m.calls.clear()
        self.install()
        self.assertEqual(self.m.path("/etc/fstab").read_text(), original)
        self.assertFalse(any(c[0] in {"dd", "mkswap", "swapoff"} for c in self.m.calls))
        self.assertEqual(self.m.path("/etc/default/grub").read_text().count(policy.BEGIN), 1)

    def test_ram_upgrade_does_not_rename_an_active_file(self):
        self.install()
        self.m.path("/proc/meminfo").write_text("MemTotal: 12289 kB\n")
        self.m.calls.clear()
        self.install()
        name = next(n for n, k in self.m.swaps.items() if k == "file")
        self.assertTrue(name.startswith("/home/.gaming-swap/swapfile-"))
        self.assertEqual(self.m.path(name).stat().st_size % 4096, 0)
        self.assertFalse(self.m.path("/home/.gaming-swap/swapfile").exists())

    def test_swapon_failure_preserves_original_swap_and_settings(self):
        self.m.fail_command = lambda a: a[0] == "swapon" and a[1] != "--show"
        original = self.m.path("/etc/fstab").read_text()
        with self.assertRaises(subprocess.CalledProcessError):
            self.install()
        self.assertTrue(self.m.path("/home/swapfile").exists())
        self.assertIn("/dev/zram0", self.m.swaps)
        self.assertEqual(self.m.path("/etc/fstab").read_text(), original)
        self.assertFalse(self.m.path("/home/.gaming-swap/swapfile").exists())

    def test_swapoff_failure_keeps_original_file_and_new_backend(self):
        self.m.fail_command = lambda a: a[:2] == ("swapoff", "/home/swapfile")
        original = self.m.path("/etc/fstab").read_text()
        with self.assertRaises(subprocess.CalledProcessError):
            self.install()
        self.assertTrue(self.m.path("/home/swapfile").exists())
        self.assertIn("/home/.gaming-swap/swapfile", self.m.swaps)
        self.assertEqual(self.m.path("/etc/fstab").read_text(), original)
        self.assertFalse(self.m.path("/etc/modprobe.d/99-gaming-swap.conf").exists())

    def test_low_disk_space_preserves_existing_swap(self):
        with patch.object(policy.shutil, "disk_usage", return_value=type("Disk", (), {"free": 1})()):
            with self.assertRaisesRegex(policy.MigrationError, "Not enough free space"):
                self.m.install()
        self.assertTrue(self.m.path("/home/swapfile").exists())
        self.assertFalse(any(c[0] == "swapoff" for c in self.m.calls))

    def test_unrecognized_file_and_symbolic_link_are_not_deleted(self):
        old = self.m.path("/home/swapfile")
        old.write_text("user data")
        with self.assertRaisesRegex(policy.MigrationError, "without a swap signature"):
            self.install()
        self.assertEqual(old.read_text(), "user data")
        old.unlink()
        old.symlink_to("/etc/passwd")
        with self.assertRaisesRegex(policy.MigrationError, "symbolic-link"):
            self.install()
        self.assertTrue(old.is_symlink())

    def test_btrfs_creation_and_extent_validation_precede_activation(self):
        self.m.filesystem = "btrfs"
        self.install()
        commands = [c[:3] for c in self.m.calls]
        self.assertIn(("btrfs", "subvolume", "create"), commands)
        self.assertIn(("btrfs", "filesystem", "mkswapfile"), commands)
        self.assertIn(("btrfs", "inspect-internal", "map-swapfile"), commands)
        self.assertNotIn("dd", [c[0] for c in self.m.calls])

    def test_btrfs_layout_failure_preserves_old_swap(self):
        self.m.filesystem = "btrfs"
        self.m.fail_command = lambda a: a[:3] == ("btrfs", "inspect-internal", "map-swapfile")
        with self.assertRaises(subprocess.CalledProcessError):
            self.install()
        self.assertTrue(self.m.path("/home/swapfile").exists())
        self.assertFalse(self.m.path("/home/.gaming-swap/swapfile").exists())

    def test_escaped_fstab_swapfile_and_custom_swap_unit(self):
        self.m.make_swap("/home/old swap", 1024**2)
        with self.m.path("/etc/fstab").open("a") as f:
            f.write("/home/old\\040swap none swap defaults 0 0\n")
        self.install()
        self.assertFalse(self.m.path("/home/old swap").exists())
        self.assertNotIn("old\\040swap", self.m.path("/etc/fstab").read_text())

    def test_runtime_uses_exact_values_and_tolerates_removed_zpool_api(self):
        self.m.runtime()
        for key in policy.PARAMETERS.keys() - {"zpool"}:
            self.assertEqual(self.m.path("/sys/module/zswap/parameters/" + key).read_text().strip(), policy.PARAMETERS[key])
        self.m.path("/sys/module/zswap/parameters/zpool").write_text("zbud")
        self.m.runtime()
        self.assertEqual(self.m.path("/sys/module/zswap/parameters/zpool").read_text().strip(), "zsmalloc")
        self.assertFalse(any(c[0] in {"dd", "mkswap", "swapoff"} for c in self.m.calls))

    def test_grub_policy_removes_conflicts_preserves_other_args(self):
        text = policy.grub_policy(self.m.path("/etc/default/grub").read_text())
        config = self.m.path("/etc/default/grub")
        config.write_text(text)
        result = subprocess.run(["sh", "-c", '. "$1"; printf "%s %s" "$GRUB_CMDLINE_LINUX" "$GRUB_CMDLINE_LINUX_DEFAULT"', "sh", str(config)], check=True, capture_output=True, text=True)
        actual = result.stdout.split()
        for argument in policy.CMDLINE:
            self.assertEqual(actual.count(argument), 1)
        self.assertIn("module_blacklist=bad_driver,zram", actual)
        self.assertIn("quiet", actual)
        self.assertIn("splash", actual)
        self.assertNotIn("zswap.enabled=0", actual)
        self.assertNotIn("systemd.zram=1", actual)
        self.assertEqual(policy.grub_policy(text), text)


if __name__ == "__main__":
    unittest.main()
