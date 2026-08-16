#!/usr/bin/env python3
"""Fail a build if a versioned patch family is not using its newest upstream release."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESOLVER_PATH = ROOT / "automation/resolve-latest-patches.py"
SPEC = importlib.util.spec_from_file_location("charcoal_patch_resolver", RESOLVER_PATH)
if SPEC is None or SPEC.loader is None:
    raise SystemExit(f"unable to load resolver: {RESOLVER_PATH}")
resolver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resolver
SPEC.loader.exec_module(resolver)

TRACKED_VERSIONED = {
    "lru_marie",
    "zram_ir",
    "adios",
    "bore",
    "poc_selector",
    "nap",
}
TRACKED_LOCAL_BYTES = {
    "zram_ir",
    "adios",
    "bore",
    "bore_sched_ext_coexistence",
    "nap",
}


def load_policy() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = json.loads(
        (ROOT / "automation/patch-sources.json").read_text(encoding="utf-8")
    )
    overrides_path = ROOT / "automation/patch-source-overrides.json"
    if overrides_path.is_file():
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        for group_name in ("components", "auxiliary_components"):
            by_name = {
                str(item.get("name", "")): item
                for item in manifest.get(group_name, [])
                if isinstance(item, dict)
            }
            for name, values in overrides.get(group_name, {}).items():
                if name in by_name and isinstance(values, dict):
                    by_name[name].update(values)
    specs = {
        str(item["name"]): item
        for group_name in ("components", "auxiliary_components")
        for item in manifest.get(group_name, [])
    }
    return manifest, specs


def selected_project_version(item: dict[str, Any]) -> str | None:
    if item.get("project_version"):
        return str(item["project_version"])
    upstream = item.get("upstream") or {}
    value = upstream.get("project_version")
    return str(value) if value else None


def main() -> int:
    _, specs = load_policy()
    lock_path = ROOT / "logs/patch-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    kernel_version = str(lock["kernel"]["version"])
    token = os.environ.get("GITHUB_TOKEN")
    locked = {
        **lock.get("components", {}),
        **lock.get("auxiliary_components", {}),
    }

    failures: list[str] = []
    for name in sorted(TRACKED_VERSIONED):
        spec = specs[name]
        candidates = resolver.upstream_candidates(spec, kernel_version, token)
        versioned = [item for item in candidates if item.project_version]
        if not versioned:
            failures.append(f"{name}: upstream exposes no versioned candidates")
            continue
        latest = max(versioned, key=resolver.latest_key)
        latest_version = str(latest.project_version)
        selected_version = selected_project_version(locked[name])
        if resolver.version_key(selected_version) != resolver.version_key(latest_version):
            failures.append(
                f"{name}: selected {selected_version or 'unknown'} but upstream latest is "
                f"{latest_version} ({latest.path})"
            )
        else:
            print(
                f"{name}: latest project version {latest_version} confirmed; "
                f"selected={selected_version}; newest_path={latest.path}"
            )

    for name in sorted(TRACKED_LOCAL_BYTES):
        item = locked[name]
        if item.get("origin") != "local-port":
            continue
        spec = specs[name]
        expected = spec.get("local_port_upstream_sha256")
        actual = (item.get("upstream") or {}).get("sha256")
        if not expected:
            failures.append(
                f"{name}: local port must pin local_port_upstream_sha256 to detect "
                "same-version upstream changes"
            )
        elif actual != expected:
            failures.append(
                f"{name}: local port tracks upstream {expected}, current lock uses {actual}"
            )
        else:
            print(f"{name}: local port upstream SHA-256 confirmed: {actual}")

    if failures:
        for failure in failures:
            print(f"latest-patch policy error: {failure}", file=sys.stderr)
        return 2
    print("All versioned patch families use their latest upstream project release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
