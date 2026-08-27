#!/usr/bin/env python3
"""Keep the latest compiler-optimization payload tracked on SteamOS 6.18."""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CpuOptimizationsPortTests(unittest.TestCase):
    def test_cpu_optimizations_port_tracks_the_latest_upstream_payload(self) -> None:
        manifest = json.loads(
            (ROOT / "automation/patch-sources.json").read_text(encoding="utf-8")
        )
        component = next(
            item
            for item in manifest["auxiliary_components"]
            if item["name"] == "cpu_optimizations"
        )

        self.assertEqual(component["port_for_kernel"], "6.18")
        self.assertTrue(component["port_when_incompatible"])
        self.assertEqual(
            component["local_port"], "6.18.45-cpu-optimizations.port.patch"
        )
        self.assertEqual(component["local_port_project_version"], "6.16")
        self.assertEqual(
            component["local_port_upstream_sha256"],
            "ed36bcab65f959200c91991e3337fd716883ef0915fbec65d6252f09fd72c666",
        )

        port = ROOT / component["local_port"]
        payload = port.read_bytes()
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            component["local_port_upstream_sha256"],
        )
        for marker in (
            b"config MZEN5",
            b"config X86_64_VERSION",
            b"CONFIG_MZEN4",
            b"KBUILD_CFLAGS += -march=znver4",
        ):
            self.assertIn(marker, payload)

        subprocess.run(
            ["git", "apply", "--numstat", str(port)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
