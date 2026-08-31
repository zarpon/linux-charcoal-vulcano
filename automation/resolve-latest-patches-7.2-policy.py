#!/usr/bin/env python3
"""SteamOS 7.2 patch policy entry point.

Policy:
- resolve the newest official SteamOS 7.2 package/tag;
- resolve the newest upstream project release before considering compatibility;
- prefer a native 7.2 variant inside that newest release;
- otherwise choose the chronologically closest kernel variant and require a
  tracked local/adaptive port;
- for HTTP patches with a reviewed local port, materialize the port bytes while
  retaining an exact SHA-256 lock to the upstream bytes that were ported.
"""
from __future__ import annotations

import hashlib
import importlib.util
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


RESOLVER.BASE.nearest_candidate = nearest_candidate_72
RESOLVER.BASE.resolve_http_component = resolve_http_component_72


if __name__ == "__main__":
    try:
        raise SystemExit(RESOLVER.main())
    except RESOLVER.BASE.ResolveError as exc:
        print(f"7.2 resolver error: {exc}", file=sys.stderr)
        raise SystemExit(2)
