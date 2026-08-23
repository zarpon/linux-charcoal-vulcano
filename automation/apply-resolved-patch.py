#!/usr/bin/env python3
"""Apply one resolved patch while enforcing native-first port fallbacks.

The resolver always writes the newest upstream native-series patch to the
``latest-*.patch`` target.  This helper proves that patch applies to the exact
Valve source tree before applying it.  Only an explicit, locked fallback may
be used after that proof fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class ApplyError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApplyError(f"unable to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ApplyError(f"{path} must contain a JSON object")
    return value


def components(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = load_json(root / "automation/patch-sources.json")
    override_path = root / "automation/patch-source-overrides.json"
    if override_path.is_file():
        overrides = load_json(override_path)
        if overrides.get("schema") != 1:
            raise ApplyError("unsupported patch source override schema")
        for group in ("components", "auxiliary_components"):
            by_name = {
                str(item.get("name", "")): item
                for item in manifest.get(group, [])
                if isinstance(item, dict)
            }
            configured = overrides.get(group, {})
            if not isinstance(configured, dict):
                raise ApplyError(f"override group {group!r} must be an object")
            for name, values in configured.items():
                if name not in by_name or not isinstance(values, dict):
                    raise ApplyError(f"invalid override for {group}.{name}")
                by_name[name].update(values)
    result = {
        str(item.get("name", "")): item
        for group in ("components", "auxiliary_components")
        for item in manifest.get(group, [])
        if isinstance(item, dict)
    }
    return manifest, result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_apply(tree: Path, patch: Path, *, check: bool) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(tree), "apply", "--recount"]
    if check:
        command.append("--check")
    command.append(str(patch))
    return subprocess.run(command, check=False, text=True, capture_output=True)


def apply_checked(tree: Path, patch: Path) -> tuple[bool, str]:
    checked = git_apply(tree, patch, check=True)
    if checked.returncode:
        return False, checked.stderr.strip() or checked.stdout.strip()
    applied = git_apply(tree, patch, check=False)
    if applied.returncode:
        raise ApplyError(
            f"git apply unexpectedly failed for {patch}: "
            f"{applied.stderr.strip() or applied.stdout.strip()}"
        )
    return True, ""


def require_port_kernel(name: str, spec: dict[str, Any], kernel_version: str) -> None:
    port_kernel = spec.get("port_for_kernel")
    if not isinstance(port_kernel, str) or not port_kernel:
        raise ApplyError(f"{name}: reviewed port has no port_for_kernel")
    if port_kernel != kernel_version:
        raise ApplyError(
            f"{name}: reviewed port targets SteamOS {port_kernel}, but this build uses "
            f"{kernel_version}; refresh and validate the port first"
        )


def require_local_port_lineage(
    name: str,
    spec: dict[str, Any],
    upstream: dict[str, Any],
    upstream_digest: Any,
    kernel_version: str,
) -> None:
    require_port_kernel(name, spec, kernel_version)
    expected_sha = spec.get("local_port_upstream_sha256")
    if not isinstance(expected_sha, str) or not expected_sha:
        raise ApplyError(f"{name}: reviewed local port has no upstream SHA-256 pin")
    if upstream_digest != expected_sha:
        raise ApplyError(
            f"{name}: reviewed local port follows upstream {expected_sha}, but the "
            f"resolved source is {upstream_digest!r}"
        )
    expected_version = spec.get("local_port_project_version")
    if expected_version and upstream.get("project_version") != expected_version:
        raise ApplyError(
            f"{name}: reviewed local port is for project version {expected_version}, "
            f"but the resolved source is {upstream.get('project_version')!r}"
        )


def require_fallback(
    name: str,
    spec: dict[str, Any],
    record: dict[str, Any],
    kernel_version: str,
) -> dict[str, Any]:
    fallback = record.get("fallback")
    if not isinstance(fallback, dict):
        raise ApplyError(f"{name}: native patch failed and no reviewed fallback is locked")
    if spec.get("local_port"):
        if fallback.get("kind") != "local-port" or fallback.get("path") != spec.get(
            "local_port"
        ):
            raise ApplyError(f"{name}: locked local-port fallback differs from the manifest")
        if fallback.get("kernel_version") != kernel_version:
            raise ApplyError(f"{name}: locked local-port fallback targets another SteamOS source")
        if fallback.get("upstream_sha256") != spec.get("local_port_upstream_sha256"):
            raise ApplyError(f"{name}: locked local-port fallback has a stale upstream pin")
        require_local_port_lineage(name, spec, record, record.get("sha256"), kernel_version)
        return fallback
    if spec.get("adaptive_port"):
        if (
            fallback.get("kind") != "adaptive-port"
            or fallback.get("adapter") != spec.get("adaptive_port")
            or fallback.get("kernel_version") != kernel_version
        ):
            raise ApplyError(f"{name}: locked adaptive fallback differs from the manifest")
        require_port_kernel(name, spec, kernel_version)
        return fallback
    raise ApplyError(f"{name}: lock declares a fallback without a manifest port")


def apply_adaptive_port(
    root: Path,
    tree: Path,
    patch: Path,
    name: str,
    adapter: str,
) -> None:
    if adapter != "poc-selector-valve":
        raise ApplyError(f"{name}: unsupported adaptive port adapter {adapter!r}")
    adapter_script = root / "automation/port-poc-selector.py"
    with tempfile.TemporaryDirectory(prefix="charcoal-patch-") as directory:
        output = Path(directory) / f"{name}.patch"
        command = [
            sys.executable,
            str(adapter_script),
            str(patch),
            str(output),
            str(tree / "kernel/sched/sched.h"),
            str(tree / "kernel/sched/fair.c"),
        ]
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        if result.returncode:
            raise ApplyError(
                f"{name}: adaptive port failed: {result.stderr.strip() or result.stdout.strip()}"
            )
        applied, details = apply_checked(tree, output)
        if not applied:
            raise ApplyError(f"{name}: adapted patch does not apply: {details}")


def resolve_record(
    root: Path, target: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    _, specs = components(root)
    lock = load_json(root / "logs/patch-lock.json")
    kernel = lock.get("kernel")
    if not isinstance(kernel, dict) or not isinstance(kernel.get("version"), str):
        raise ApplyError("patch lock has no selected SteamOS kernel version")
    for group in ("components", "auxiliary_components"):
        records = lock.get(group, {})
        if not isinstance(records, dict):
            continue
        for name, record in records.items():
            if isinstance(record, dict) and record.get("target") == target:
                spec = specs.get(name)
                if not isinstance(spec, dict):
                    raise ApplyError(f"{name}: patch lock has no manifest component")
                return spec, record, kernel, str(name)
    raise ApplyError(f"no patch-lock entry matches {target}")


def apply_component(root: Path, tree: Path, patch: Path, target: str) -> str:
    spec, record, kernel, name = resolve_record(root, target)
    if not patch.is_file():
        raise ApplyError(f"{name}: resolved patch is missing: {patch}")
    expected_digest = record.get("sha256")
    if not isinstance(expected_digest, str) or sha256(patch) != expected_digest:
        raise ApplyError(f"{name}: resolved patch bytes do not match patch-lock.json")

    kernel_version = str(kernel["version"])
    origin = record.get("origin")
    if origin == "local-port":
        upstream = record.get("upstream")
        if not isinstance(upstream, dict):
            raise ApplyError(f"{name}: local port has no upstream lock")
        require_local_port_lineage(
            name, spec, upstream, upstream.get("sha256"), kernel_version
        )
        applied, details = apply_checked(tree, patch)
        if not applied:
            raise ApplyError(f"{name}: reviewed local port does not apply: {details}")
        return "local-port"

    if origin == "adaptive-port":
        adapter = record.get("adapter")
        if adapter != spec.get("adaptive_port"):
            raise ApplyError(f"{name}: adaptive port adapter differs from the manifest")
        require_port_kernel(name, spec, kernel_version)
        apply_adaptive_port(root, tree, patch, name, str(adapter))
        return "adaptive-port"

    applied, details = apply_checked(tree, patch)
    if applied:
        return "upstream-native" if origin == "upstream-native" else "upstream"

    fallback = require_fallback(name, spec, record, kernel_version)
    if fallback["kind"] == "local-port":
        fallback_patch = root / str(fallback["path"])
        if not fallback_patch.is_file():
            raise ApplyError(f"{name}: reviewed fallback port is missing: {fallback_patch}")
        port_applied, port_details = apply_checked(tree, fallback_patch)
        if not port_applied:
            raise ApplyError(
                f"{name}: native patch does not apply ({details}); reviewed fallback also "
                f"does not apply ({port_details})"
            )
        return "local-port-fallback"
    if fallback["kind"] == "adaptive-port":
        apply_adaptive_port(root, tree, patch, name, str(fallback["adapter"]))
        return "adaptive-port-fallback"
    raise ApplyError(f"{name}: unsupported locked fallback kind {fallback['kind']!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    tree = args.tree.resolve()
    patch = args.patch.resolve()
    method = apply_component(root, tree, patch, str(args.target))
    print(f"{args.target}: applied via {method}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApplyError as exc:
        print(f"resolved-patch application error: {exc}", file=sys.stderr)
        raise SystemExit(2)
