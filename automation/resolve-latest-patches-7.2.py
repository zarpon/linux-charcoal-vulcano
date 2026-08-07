#!/usr/bin/env python3
"""SteamOS 7.2 entry point for the shared dynamic patch resolver.

The shared resolver remains compatible with the 6.16 production branch.  This
entry point adds two 7.2 requirements without changing that branch:

* use the exact Valve tag selected from the official linux-neptune-72 package;
* use kernel series 7.2 for patch compatibility even while the tag is an RC.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "automation/resolve-latest-patches.py"
SPEC = importlib.util.spec_from_file_location("charcoal_shared_patch_resolver", BASE_PATH)
if not SPEC or not SPEC.loader:
    raise RuntimeError(f"unable to load {BASE_PATH}")
BASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BASE
SPEC.loader.exec_module(BASE)


class Resolve72Error(BASE.ResolveError):
    pass


def preferred_kernel_tag(config: dict[str, Any], token: str | None) -> tuple[str, str]:
    preferred = str(config.get("preferred_tag", "")).strip()
    if not preferred:
        if config.get("allow_prerelease"):
            raise Resolve72Error(
                "7.2 manifest must contain preferred_tag selected from the official source index"
            )
        return BASE.resolve_kernel_tag(config, token)

    pattern = re.compile(str(config["tag_regex"]))
    match = pattern.fullmatch(preferred)
    if not match:
        raise Resolve72Error(f"preferred Valve tag does not match policy: {preferred}")
    if "-rc" in preferred.lower() and not config.get("allow_prerelease"):
        raise Resolve72Error(f"release candidate is not allowed by manifest: {preferred}")

    encoded = urllib.parse.quote(preferred, safe="")
    refs = BASE.request_json(
        f"{BASE.API}/repos/{config['repository']}/git/matching-refs/tags/{encoded}",
        token,
    )
    if not isinstance(refs, list):
        raise Resolve72Error("expected a list from matching tag refs")
    exact_ref = f"refs/tags/{preferred}"
    item = next((entry for entry in refs if entry.get("ref") == exact_ref), None)
    if not item:
        raise Resolve72Error(f"official package tag is absent upstream: {preferred}")
    obj = item.get("object", {})
    sha = obj.get("sha")
    if not sha:
        raise Resolve72Error(f"upstream tag has no object SHA: {preferred}")
    if obj.get("type") == "tag" and obj.get("url"):
        tag = BASE.request_json(obj["url"], token)
        sha = tag.get("object", {}).get("sha", sha)
    return preferred, str(sha)


def apply_overrides(manifest: dict[str, Any], override_path: Path) -> None:
    if not override_path.is_file():
        return
    overrides = json.loads(override_path.read_text(encoding="utf-8"))
    if overrides.get("schema") != 1:
        raise Resolve72Error("unsupported patch source override schema")
    for group_name in ("components", "auxiliary_components"):
        configured = overrides.get(group_name, {})
        if not isinstance(configured, dict):
            raise Resolve72Error(f"override group {group_name!r} must be an object")
        by_name = {
            str(item.get("name", "")): item
            for item in manifest.get(group_name, [])
            if isinstance(item, dict)
        }
        for name, values in configured.items():
            if name not in by_name or not isinstance(values, dict):
                raise Resolve72Error(f"invalid override for {group_name}.{name}")
            by_name[name].update(values)


def kernel_series(manifest: dict[str, Any]) -> str:
    source = manifest.get("kernel_source", {})
    series = str(source.get("series", "")).strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+", series):
        raise Resolve72Error("kernel_source.series must be a major.minor value")
    if not series.startswith("7.2"):
        raise Resolve72Error(f"this resolver only supports SteamOS 7.2, got {series}")
    return series


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="logs/patch-sources-7.2.json")
    parser.add_argument("--overrides", default="automation/patch-source-overrides-7.2.json")
    parser.add_argument("--pkgbuild", default="PKGBUILD")
    parser.add_argument("--lock", default="logs/patch-lock.json")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fixture")
    args = parser.parse_args()

    root = Path.cwd()
    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    apply_overrides(manifest, root / args.overrides)
    groups = BASE.validate_manifest(manifest)
    all_components = groups["components"] + groups["auxiliary_components"]
    series = kernel_series(manifest)
    pkgbuild_path = root / args.pkgbuild
    pkgbuild = pkgbuild_path.read_text(encoding="utf-8")
    token = os.environ.get("GITHUB_TOKEN")

    if args.fixture:
        fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        kernel_tag = fixture["kernel_tag"]
        kernel_sha = fixture.get("kernel_sha", "fixture")
        selected_groups = {
            name: fixture.get(name, {})
            for name in ("components", "auxiliary_components")
        }
    else:
        kernel_tag, kernel_sha = preferred_kernel_tag(manifest["kernel_source"], token)
        selected_groups = {
            name: {
                spec["name"]: BASE.resolve_component(spec, series, token, root)
                for spec in specs
            }
            for name, specs in groups.items()
        }

    lock: dict[str, Any] = {
        "schema": 3,
        "kernel": {"tag": kernel_tag, "version": series, "commit": kernel_sha},
        "components": {},
        "auxiliary_components": {},
    }
    replacements: dict[str, str] = {}
    for group_name, specs in groups.items():
        selected = selected_groups[group_name]
        for spec in specs:
            name = spec["name"]
            target = spec["target"]
            item = selected[name]
            if "content_bytes" in item:
                data = item["content_bytes"]
            elif args.fixture:
                data = item.get("content", "fixture patch\n").encode()
            elif item.get("origin") == "local-port":
                data = (root / item["path"]).read_bytes()
            else:
                data = BASE.request_bytes(item["url"], token)
            if not (BASE.looks_like_patch(data) or data.startswith(b"fixture")):
                raise Resolve72Error(f"patch for {name} does not look valid")
            clean = {
                key: value
                for key, value in item.items()
                if key not in {"content_bytes", "content"}
            }
            lock[group_name][name] = {
                **clean,
                "target": target,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
            replacements[name] = target
            if args.write:
                (root / target).write_bytes(data)

    updated = BASE.replace_assignment(pkgbuild, "_tag", kernel_tag)
    updated = BASE.replace_source_entries(updated, all_components, replacements)
    updated = BASE.replace_sha_array_with_skip(updated)
    if args.write:
        pkgbuild_path.write_text(updated, encoding="utf-8")

    lock_path = root / args.lock
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(lock, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BASE.ResolveError as exc:
        print(f"7.2 resolver error: {exc}", file=sys.stderr)
        raise SystemExit(2)
