#!/usr/bin/env python3
"""Harden the Charcoal build workflow against cancellation deadlocks."""

from __future__ import annotations

import argparse
from pathlib import Path

OLD_BLOCK = """concurrency:
  group: charcoal-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
"""

NEW_BLOCK = """# Use an isolated key for every run. GitHub has returned persistent HTTP 500
# errors while cancelling old runs; a stale run must never block a newer build.
concurrency:
  group: charcoal-${{ github.workflow }}-${{ github.run_id }}
  cancel-in-progress: false
"""


def harden(content: str) -> tuple[str, bool]:
    if NEW_BLOCK in content:
        return content, False
    if OLD_BLOCK not in content:
        raise ValueError("expected Charcoal concurrency block was not found")
    updated = content.replace(OLD_BLOCK, NEW_BLOCK, 1)
    if updated.count("cancel-in-progress:") != 1:
        raise ValueError("unexpected additional cancel-in-progress declarations")
    return updated, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    args = parser.parse_args()

    original = args.workflow.read_text(encoding="utf-8")
    updated, changed = harden(original)
    if changed:
        args.workflow.write_text(updated, encoding="utf-8")
        print(f"hardened {args.workflow}")
    else:
        print(f"{args.workflow} is already hardened")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
