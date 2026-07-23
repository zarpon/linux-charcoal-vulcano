#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "patch_lock_validation", ROOT / "automation/validate-patch-lock.py"
)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def manifest(version: str = "2.6.1r2") -> dict:
    return {
        "schema": 2,
        "components": [
            {
                "name": "poc_selector",
                "kind": "github_tree",
                "target": "latest-poc-selector.patch",
                "local_port": "6.16-poc-selector-v2.6.1r2.patch",
                "local_port_project_version": version,
                "project_version_regex": "poc-selector-v(?P<version>.+)\\.patch$",
            }
        ],
        "auxiliary_components": [],
    }


def lock(version: str = "2.6.1r2") -> dict:
    return {
        "schema": 3,
        "components": {
            "poc_selector": {
                "origin": "local-port",
                "target": "latest-poc-selector.patch",
                "sha256": "a" * 64,
                "size": 1,
                "upstream": {
                    "repository": "firelzrd/poc-selector",
                    "path": "patches/stable/0001-6.18.3-poc-selector-v2.6.1r2.patch",
                    "commit": "b" * 40,
                    "url": "https://example.invalid/poc.patch",
                    "project_version": version,
                    "sha256": "c" * 64,
                    "size": 1,
                },
            }
        },
        "auxiliary_components": {},
    }


class PatchLockValidationTests(unittest.TestCase):
    def test_current_local_port_passes(self) -> None:
        validator.validate(manifest(), lock())

    def test_stale_local_port_is_rejected(self) -> None:
        with self.assertRaisesRegex(validator.ValidationError, "stale"):
            validator.validate(manifest("2.6.1"), lock("2.6.1r2"))

    def test_missing_auxiliary_component_is_rejected(self) -> None:
        current_manifest = manifest()
        current_manifest["auxiliary_components"] = [
            {"name": "clear", "kind": "http_patch", "target": "latest-clear.patch"}
        ]
        with self.assertRaisesRegex(validator.ValidationError, "missing"):
            validator.validate(current_manifest, lock())


if __name__ == "__main__":
    unittest.main()
