#!/usr/bin/env python3
"""Audit every GitHub patch family against the newest upstream source.

The policy is intentionally two-stage: identify the newest upstream project
release first, then prefer its native target-kernel-series variant. If that
newest project release has no native variant, the reviewed port must track the
chronologically nearest kernel variant of that same newest release.
"""
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


def kernel_ordinal(version: tuple[int, ...]) -> int:
    padded = version + (0,) * (3 - len(version))
    return padded[0] * 1_000_000 + padded[1] * 1_000 + padded[2]


def nearest_candidate_chronological(candidates, kernel_version: str):
    """Choose the numerically nearest kernel line across major boundaries.

    Independent |major| + |minor| distances are incorrect at a major-version
    boundary: they can rank 6.12 closer to 7.2 than 6.19 and 6.3 closer than
    6.11. This ordered coordinate matches the SteamOS 7.2 resolver policy.
    """
    target = resolver.parse_kernel_version(kernel_version)
    if target is None:
        raise resolver.ResolveError(f"invalid kernel version: {kernel_version}")
    target_value = kernel_ordinal(target)
    versioned = [item for item in candidates if item.kernel_version]
    if not versioned:
        return None

    def distance(item) -> int:
        return abs(kernel_ordinal(item.kernel_version) - target_value)

    minimum = min(distance(item) for item in versioned)
    return max(
        (item for item in versioned if distance(item) == minimum),
        key=resolver.latest_key,
    )


def load_policy(
    manifest_path: Path, overrides_path: Path
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
                    for key, value in values.items():
                        if value is None:
                            by_name[name].pop(key, None)
                        else:
                            by_name[name][key] = value
    specs = {
        str(item["name"]): item
        for group_name in ("components", "auxiliary_components")
        for item in manifest.get(group_name, [])
        if item.get("kind", "github_tree") == "github_tree"
    }
    return manifest, specs


def policy_paths(kernel_version: str) -> tuple[Path, Path]:
    """Select the policy that produced the lock being audited.

    The 7.2 workflow writes its prepared manifest under logs so the shared
    validator can audit the exact dynamically resolved policy instead of
    accidentally auditing the 6.18/default manifest.
    """
    prepared_72 = ROOT / "logs/patch-sources-7.2.json"
    if kernel_version.startswith("7.2") and prepared_72.is_file():
        return prepared_72, ROOT / "automation/patch-source-overrides-7.2.json"
    return (
        ROOT / "automation/patch-sources.json",
        ROOT / "automation/patch-source-overrides.json",
    )


def upstream_record(item: dict[str, Any]) -> dict[str, Any]:
    upstream = item.get("upstream") if item.get("origin") == "local-port" else item
    return upstream if isinstance(upstream, dict) else {}


def selected_project_version(item: dict[str, Any]) -> str | None:
    value = upstream_record(item).get("project_version")
    return str(value) if value else None


def expected_port_selection(spec: dict[str, Any]) -> tuple[str, str] | None:
    if spec.get("local_port"):
        return "latest-release-port", "local-port"
    if spec.get("adaptive_port"):
        return "latest-release-adaptive-port", "adaptive-port"
    return None


def kernel_series(kernel_version: str) -> str:
    parsed = resolver.parse_kernel_version(kernel_version)
    if parsed is None or len(parsed) < 2:
        return kernel_version
    return f"{parsed[0]}.{parsed[1]}"


def audit_component(
    name: str,
    spec: dict[str, Any],
    record: dict[str, Any],
    kernel_version: str,
    token: str | None,
) -> list[str]:
    failures: list[str] = []
    target_series = kernel_series(kernel_version)
    try:
        candidates = resolver.upstream_candidates(spec, kernel_version, token)
    except resolver.ResolveError as exc:
        return [f"{name}: unable to inspect upstream candidates: {exc}"]
    if not candidates:
        return [f"{name}: upstream exposes no candidate patches"]

    latest = resolver.latest_project_candidates(candidates)
    upstream = upstream_record(record)
    versioned = [candidate for candidate in latest if candidate.project_version]
    if versioned:
        latest_version = max(versioned, key=resolver.latest_key).project_version
        selected_version = selected_project_version(record)
        if resolver.project_version_key(selected_version) != resolver.project_version_key(
            latest_version
        ):
            failures.append(
                f"{name}: selected {selected_version or 'unknown'} but newest upstream "
                f"release is {latest_version}"
            )

    native = resolver.native_series_candidates(latest)
    if native:
        expected = max(native, key=resolver.compatible_key)
        if (
            record.get("selection") != "latest-native-series"
            or record.get("origin") != "upstream-native"
        ):
            failures.append(
                f"{name}: newest release has native {target_series} patches, but the "
                "lock does not select the native source first"
            )
        elif upstream.get("path") != expected.path or upstream.get("commit") != expected.sha:
            failures.append(
                f"{name}: native selection differs from newest compatible upstream "
                f"candidate {expected.path}"
            )
        else:
            print(f"{name}: newest release selected with native source {expected.path}")
        return failures

    if any(candidate.kernel_version for candidate in latest):
        expected = nearest_candidate_chronological(latest, kernel_version)
        policy = expected_port_selection(spec)
        if expected is None or policy is None:
            failures.append(
                f"{name}: newest release has no native {target_series} patch and no "
                "reviewed port policy"
            )
            return failures
        selection, origin = policy
        if record.get("selection") != selection or record.get("origin") != origin:
            failures.append(f"{name}: newest non-native release must use its reviewed port")
        elif upstream.get("path") != expected.path or upstream.get("commit") != expected.sha:
            failures.append(
                f"{name}: port does not track the nearest upstream candidate from the "
                f"newest project release: {expected.path}"
            )
        else:
            print(
                f"{name}: newest release has no native patch; reviewed port tracks "
                f"{expected.path}"
            )
        return failures

    expected = max(latest, key=resolver.latest_key)
    if (
        record.get("selection") != "latest-kernel-agnostic"
        or record.get("origin") != "upstream-kernel-agnostic"
    ):
        failures.append(f"{name}: kernel-agnostic source policy is not locked directly")
    elif upstream.get("path") != expected.path or upstream.get("commit") != expected.sha:
        failures.append(f"{name}: kernel-agnostic source differs from {expected.path}")
    else:
        print(f"{name}: current kernel-agnostic source selected: {expected.path}")
    return failures


def main() -> int:
    lock_path = ROOT / "logs/patch-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    kernel_version = str(lock["kernel"]["version"])
    manifest_path, overrides_path = policy_paths(kernel_version)
    _, specs = load_policy(manifest_path, overrides_path)
    token = os.environ.get("GITHUB_TOKEN")
    locked = {
        **lock.get("components", {}),
        **lock.get("auxiliary_components", {}),
    }

    failures: list[str] = []
    for name, spec in sorted(specs.items()):
        record = locked.get(name)
        if not isinstance(record, dict):
            failures.append(f"{name}: lock record is missing")
            continue
        failures.extend(audit_component(name, spec, record, kernel_version, token))

    if failures:
        for failure in failures:
            print(f"latest-patch policy error: {failure}", file=sys.stderr)
        return 2
    print(
        f"Every GitHub patch family follows newest-release then native-"
        f"{kernel_series(kernel_version)}-first policy"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
