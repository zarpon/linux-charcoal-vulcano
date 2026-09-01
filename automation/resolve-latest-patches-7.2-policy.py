#!/usr/bin/env python3
"""SteamOS 7.2 patch policy entry point.

Policy:
- resolve the newest official SteamOS 7.2 package/tag;
- resolve the newest upstream project release before considering compatibility;
- prefer a native 7.2 variant inside that newest release;
- otherwise choose the chronologically closest kernel variant and require a
  tracked local/adaptive port;
- for HTTP patches with a reviewed local port, materialize the port bytes while
  retaining an exact SHA-256 lock to the upstream bytes that were ported;
- normalize the legacy 7.2 resolver output to the shared schema-5 lock contract
  so the same validator/auditor used by 618pre protects the 7.2 branch.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "automation/resolve-latest-patches-7.2.py"
SPEC = importlib.util.spec_from_file_location("charcoal_resolver_72", ENTRY)
if not SPEC or not SPEC.loader:
    raise RuntimeError(f"unable to load {ENTRY}")
RESOLVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RESOLVER
SPEC.loader.exec_module(RESOLVER)


def kernel_ordinal(version: tuple[int, ...]) -> int:
    padded = version + (0,) * (3 - len(version))
    return padded[0] * 1_000_000 + padded[1] * 1_000 + padded[2]


def nearest_candidate_72(candidates, kernel_version: str):
    target = RESOLVER.BASE.parse_kernel_version(kernel_version)
    if target is None:
        raise RESOLVER.BASE.ResolveError(f"invalid kernel version: {kernel_version}")
    target_value = kernel_ordinal(target)
    versioned = [item for item in candidates if item.kernel_version]
    if not versioned:
        return None

    def distance(item) -> int:
        return abs(kernel_ordinal(item.kernel_version) - target_value)

    minimum = min(distance(item) for item in versioned)
    return max(
        (item for item in versioned if distance(item) == minimum),
        key=RESOLVER.BASE.latest_key,
    )


def resolve_http_component_72(spec, kernel_version: str, token: str | None, root: Path):
    series = ".".join(kernel_version.split(".")[:2])
    errors: list[str] = []
    for template in spec.get("urls", []):
        url = str(template).format(kernel_version=kernel_version, series=series)
        try:
            data = RESOLVER.BASE.request_bytes(url, token)
            if spec.get("mailbox"):
                data = RESOLVER.BASE.decode_mailbox_patch(data)
            if not RESOLVER.BASE.looks_like_patch(data):
                raise RESOLVER.BASE.ResolveError("response is not a patch")
            upstream = {
                "repository": spec.get("repository", url),
                "path": spec.get("path"),
                "commit": spec.get("commit"),
                "url": url,
                "selection": "first-valid",
            }
            local_port = spec.get("local_port")
            if not local_port:
                return {
                    **upstream,
                    "origin": "upstream-fixed",
                    "content_bytes": data,
                }

            port_path = root / str(local_port)
            port_data = port_path.read_bytes() if port_path.is_file() else b""
            if not port_data or not RESOLVER.BASE.looks_like_patch(port_data):
                raise RESOLVER.BASE.ResolveError(f"local port is missing or invalid: {local_port}")

            upstream_sha = hashlib.sha256(data).hexdigest()
            expected_sha = spec.get("local_port_upstream_sha256")
            if not expected_sha:
                raise RESOLVER.BASE.ResolveError(
                    f"unversioned local port for {spec['name']} must declare local_port_upstream_sha256"
                )
            if upstream_sha != expected_sha:
                raise RESOLVER.BASE.ResolveError(
                    f"local port for {spec['name']} follows upstream SHA-256 {expected_sha}, "
                    f"but current upstream is {upstream_sha}; refresh and validate the port"
                )

            upstream["sha256"] = upstream_sha
            upstream["size"] = len(data)
            return {
                "repository": "zarpon/linux-charcoal-vulcano",
                "path": str(local_port),
                "commit": "repository-local",
                "url": None,
                "origin": "local-port",
                "selection": "first-valid-port",
                "upstream": upstream,
                "content_bytes": port_data,
            }
        except RESOLVER.BASE.ResolveError as exc:
            errors.append(f"{url}: {exc}")
    raise RESOLVER.BASE.ResolveError(
        f"no usable URL for {spec['name']}: {' | '.join(errors)}"
    )


def lock_path_from_argv(argv: list[str]) -> Path:
    """Mirror argparse's --lock option without consuming resolver arguments."""
    default = Path("logs/patch-lock.json")
    for index, value in enumerate(argv):
        if value == "--lock" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--lock="):
            return Path(value.split("=", 1)[1])
    return default


def normalize_schema5_lock(path: Path) -> None:
    """Convert the 7.2 entry point's legacy lock envelope to schema 5.

    Component records are already produced by the shared resolver and carry the
    schema-5 source/origin/lineage fields. Only the legacy top-level envelope
    still used schema 3 and stored the broad series (7.2) as kernel.version.
    Fallback records also used the broad series; schema 5 binds those fallbacks
    to the exact Valve source revision being validated while their manifest
    port scope remains series-wide.
    """
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RESOLVER.BASE.ResolveError(f"unable to normalize 7.2 patch lock {path}: {exc}") from exc

    if not isinstance(lock, dict) or not isinstance(lock.get("kernel"), dict):
        raise RESOLVER.BASE.ResolveError("7.2 patch lock has an invalid top-level structure")
    tag = lock["kernel"].get("tag")
    if not isinstance(tag, str) or "-valve" not in tag:
        raise RESOLVER.BASE.ResolveError(f"7.2 patch lock contains an invalid Valve tag: {tag!r}")
    version = tag.split("-valve", 1)[0]
    if not version.startswith("7.2"):
        raise RESOLVER.BASE.ResolveError(
            f"refusing to normalize a non-7.2 patch lock: {version!r}"
        )

    lock["schema"] = 5
    lock["kernel"]["version"] = version
    for group_name in ("components", "auxiliary_components"):
        group = lock.get(group_name, {})
        if not isinstance(group, dict):
            raise RESOLVER.BASE.ResolveError(f"7.2 patch lock group {group_name!r} is invalid")
        for name, record in group.items():
            if not isinstance(record, dict):
                raise RESOLVER.BASE.ResolveError(f"7.2 patch lock record {group_name}.{name} is invalid")
            fallback = record.get("fallback")
            if isinstance(fallback, dict) and fallback.get("kernel_version") == "7.2":
                fallback["kernel_version"] = version

    path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")


RESOLVER.BASE.nearest_candidate = nearest_candidate_72
RESOLVER.BASE.resolve_http_component = resolve_http_component_72


if __name__ == "__main__":
    try:
        status = RESOLVER.main()
        if status == 0:
            lock_path = lock_path_from_argv(sys.argv[1:])
            normalize_schema5_lock(lock_path)
            normalized = json.loads(lock_path.read_text(encoding="utf-8"))
            print("normalized 7.2 patch lock:")
            print(json.dumps(normalized, indent=2, sort_keys=True))
        raise SystemExit(status)
    except RESOLVER.BASE.ResolveError as exc:
        print(f"7.2 resolver error: {exc}", file=sys.stderr)
        raise SystemExit(2)
