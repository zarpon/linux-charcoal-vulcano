#!/usr/bin/env python3
"""Keep the newest linux-tkg fsync fallback bound to Valve 6.18.45."""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FsyncPortTests(unittest.TestCase):
    def test_fsync_port_is_a_reviewed_618_fallback(self) -> None:
        manifest = json.loads(
            (ROOT / "automation/patch-sources.json").read_text(encoding="utf-8")
        )
        fsync = next(
            item
            for item in manifest["auxiliary_components"]
            if item["name"] == "fsync"
        )

        self.assertEqual(fsync["port_for_kernel"], "6.18.45")
        self.assertTrue(fsync["port_when_incompatible"])
        self.assertNotIn("allow_nearest_upstream", fsync)
        self.assertEqual(
            fsync["local_port"], "6.18.45-fsync-futex-waitv.port.patch"
        )
        self.assertEqual(
            fsync["local_port_upstream_sha256"],
            "9df628fd530950e37d31da854cb314d536f33c83935adf5c47e71266a55f7004",
        )

        port = ROOT / fsync["local_port"]
        data = port.read_bytes()
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "0a8f3a6540dfc534ac4a9e70f3cd3c23315ad69e87b74d18c5808bcb3b482b3f",
        )
        for marker in (
            "#define FUTEX_WAIT_MULTIPLE\t31",
            "futex_read_wait_block",
            "futex_opcode_31",
            "return futex_opcode_31(tp, uaddr, val);",
        ):
            self.assertIn(marker.encode(), data)

        subprocess.run(
            ["git", "apply", "--numstat", str(port)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
