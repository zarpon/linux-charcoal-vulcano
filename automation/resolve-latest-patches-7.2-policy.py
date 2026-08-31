#!/usr/bin/env python3
"""SteamOS 7.2 patch policy entry point.

It preserves the shared 618pre rule (newest project release first, native target
variant second, tracked port otherwise) and fixes cross-major fallback ranking
for 7.x kernels.  A 7.1 source is therefore preferred over 6.19, and 6.19 over
6.18/6.12, when the newest project release has no native 7.2 variant.
"""
from __future__ import annotations

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


RESOLVER.BASE.nearest_candidate = nearest_candidate_72


if __name__ == "__main__":
    try:
        raise SystemExit(RESOLVER.main())
    except RESOLVER.BASE.ResolveError as exc:
        print(f"7.2 resolver error: {exc}", file=sys.stderr)
        raise SystemExit(2)
