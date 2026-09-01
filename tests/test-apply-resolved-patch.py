#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apply_resolved_patch", ROOT / "automation/apply-resolved-patch.py"
)
assert SPEC and SPEC.loader
applicator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = applicator
SPEC.loader.exec_module(applicator)


def patch(path: str, before: str, after: str) -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        "index 1111111..2222222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        f"-{before}\n"
        f"+{after}\n"
    ).encode()


class ResolvedPatchApplicationTests(unittest.TestCase):
    def make_root(self, direct: bytes, *, fallback: bytes | None = None) -> tuple[Path, Path]:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        (directory / "automation").mkdir()
        (directory / "logs").mkdir()
        manifest = {
            "schema": 4,
            "kernel_source": {},
            "components": [
                {
                    "name": "demo",
                    "kind": "github_tree",
                    "target": "latest-demo.patch",
                    **(
                        {
                            "local_port": "demo.port.patch",
                            "port_for_kernel": "6.18",
                            "local_port_project_version": "1.0.0",
                            "local_port_upstream_sha256": hashlib.sha256(direct).hexdigest(),
                        }
                        if fallback is not None
                        else {}
                    ),
                }
            ],
            "auxiliary_components": [],
        }
        (directory / "automation/patch-sources.json").write_text(json.dumps(manifest))
        (directory / "latest-demo.patch").write_bytes(direct)
        if fallback is not None:
            (directory / "demo.port.patch").write_bytes(fallback)

        record = {
            "origin": "upstream-native",
            "selection": "latest-native-series",
            "repository": "example/demo",
            "path": "patches/6.18-demo-1.0.0.patch",
            "commit": "a" * 40,
            "url": "https://example.invalid/demo.patch",
            "kernel_version": "6.18.22",
            "project_version": "1.0.0",
            "target": "latest-demo.patch",
            "sha256": hashlib.sha256(direct).hexdigest(),
            "size": len(direct),
        }
        if fallback is not None:
            record["fallback"] = {
                "kind": "local-port",
                "path": "demo.port.patch",
                "kernel_version": "6.18.45",
                "project_version": "1.0.0",
                "upstream_sha256": hashlib.sha256(direct).hexdigest(),
            }
        lock = {
            "schema": 5,
            "kernel": {"version": "6.18.45"},
            "components": {"demo": record},
            "auxiliary_components": {},
        }
        (directory / "logs/patch-lock.json").write_text(json.dumps(lock))

        tree = directory / "tree"
        tree.mkdir()
        (tree / "demo.txt").write_text("old\n")
        subprocess.run(["git", "init", "-q", str(tree)], check=True)
        return directory, tree

    def test_native_patch_is_applied_before_a_valid_fallback(self) -> None:
        direct = patch("demo.txt", "old", "native")
        fallback = patch("demo.txt", "old", "fallback")
        root, tree = self.make_root(direct, fallback=fallback)

        method = applicator.apply_component(
            root, tree, root / "latest-demo.patch", "latest-demo.patch"
        )

        self.assertEqual(method, "upstream-native")
        self.assertEqual((tree / "demo.txt").read_text(), "native\n")

    def test_local_port_is_used_only_after_native_apply_check_fails(self) -> None:
        direct = patch("missing.txt", "old", "native")
        fallback = patch("demo.txt", "old", "ported")
        root, tree = self.make_root(direct, fallback=fallback)

        method = applicator.apply_component(
            root, tree, root / "latest-demo.patch", "latest-demo.patch"
        )

        self.assertEqual(method, "local-port-fallback")
        self.assertEqual((tree / "demo.txt").read_text(), "ported\n")


if __name__ == "__main__":
    unittest.main()
