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


def manifest(version: str = "1.0.0") -> dict:
    return {
        "schema": 2,
        "components": [
            {
                "name": "static_port",
                "kind": "github_tree",
                "target": "latest-static-port.patch",
                "local_port": "static-port.patch",
                "local_port_project_version": version,
                "project_version_regex": "static-v(?P<version>.+)\\.patch$",
            }
        ],
        "auxiliary_components": [],
    }


def lock(version: str = "1.0.0") -> dict:
    return {
        "schema": 3,
        "components": {
            "static_port": {
                "origin": "local-port",
                "target": "latest-static-port.patch",
                "sha256": "a" * 64,
                "size": 1,
                "upstream": {
                    "repository": "example/static-port",
                    "path": "patches/stable/0001-6.18.3-static-v1.0.0.patch",
                    "commit": "b" * 40,
                    "url": "https://example.invalid/static.patch",
                    "project_version": version,
                    "sha256": "c" * 64,
                    "size": 1,
                },
            }
        },
        "auxiliary_components": {},
    }


def adaptive_manifest() -> dict:
    return {
        "schema": 2,
        "components": [
            {
                "name": "poc_selector",
                "kind": "github_tree",
                "target": "latest-poc-selector.patch",
                "adaptive_port": "poc-selector-valve",
            }
        ],
        "auxiliary_components": [],
    }


def adaptive_lock(adapter: str = "poc-selector-valve") -> dict:
    return {
        "schema": 3,
        "components": {
            "poc_selector": {
                "origin": "adaptive-port",
                "adapter": adapter,
                "repository": "firelzrd/poc-selector",
                "path": "patches/stable/0001-6.18.3-poc-selector-v2.6.3.patch",
                "commit": "b" * 40,
                "url": "https://example.invalid/poc.patch",
                "project_version": "2.6.3",
                "target": "latest-poc-selector.patch",
                "sha256": "a" * 64,
                "size": 1,
            }
        },
        "auxiliary_components": {},
    }


def http_port_manifest() -> dict:
    return {
        "schema": 2,
        "components": [],
        "auxiliary_components": [
            {
                "name": "mailing_list_port",
                "kind": "http_patch",
                "target": "latest-mailing-list-port.patch",
                "local_port": "mailing-list-port.patch",
                "local_port_upstream_sha256": "c" * 64,
            }
        ],
    }


def http_port_lock() -> dict:
    return {
        "schema": 3,
        "components": {},
        "auxiliary_components": {
            "mailing_list_port": {
                "origin": "local-port",
                "target": "latest-mailing-list-port.patch",
                "sha256": "a" * 64,
                "size": 1,
                "upstream": {
                    "repository": "lore.kernel.org/linux-pm",
                    "path": "message@example.invalid",
                    "commit": "message@example.invalid",
                    "url": "https://example.invalid/message.mbox",
                    "sha256": "c" * 64,
                    "size": 1,
                },
            }
        },
    }


class PatchLockValidationTests(unittest.TestCase):
    def test_current_local_port_passes(self) -> None:
        validator.validate(manifest(), lock())

    def test_stale_local_port_is_rejected(self) -> None:
        with self.assertRaisesRegex(validator.ValidationError, "stale"):
            validator.validate(manifest("0.9.0"), lock("1.0.0"))

    def test_missing_auxiliary_component_is_rejected(self) -> None:
        current_manifest = manifest()
        current_manifest["auxiliary_components"] = [
            {"name": "clear", "kind": "http_patch", "target": "latest-clear.patch"}
        ]
        with self.assertRaisesRegex(validator.ValidationError, "missing"):
            validator.validate(current_manifest, lock())

    def test_adaptive_port_locks_current_upstream_source(self) -> None:
        validator.validate(adaptive_manifest(), adaptive_lock())

    def test_adaptive_port_rejects_an_unexpected_adapter(self) -> None:
        with self.assertRaisesRegex(validator.ValidationError, "adapter"):
            validator.validate(adaptive_manifest(), adaptive_lock("different-adapter"))

    def test_local_http_port_requires_complete_upstream_lock(self) -> None:
        validator.validate(http_port_manifest(), http_port_lock())
        incomplete = http_port_lock()
        del incomplete["auxiliary_components"]["mailing_list_port"]["upstream"]["size"]
        with self.assertRaisesRegex(validator.ValidationError, "upstream size"):
            validator.validate(http_port_manifest(), incomplete)


if __name__ == "__main__":
    unittest.main()
