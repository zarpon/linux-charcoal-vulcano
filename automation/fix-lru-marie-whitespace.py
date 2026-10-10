#!/usr/bin/env python3
"""Normalize one malformed continuation indent in LRU Marie 0.12.0."""
from __future__ import annotations

import argparse
from pathlib import Path

PREFIX = "\t\tif (referenced_ptes > 0 && (vm_flags & VM_EXEC) &&\n"
BAD = PREFIX + "\t\t    \t\t\t\t\t\tfolio_is_file_lru(folio))"
GOOD = PREFIX + "\t\t    folio_is_file_lru(folio))"


class CompatibilityError(RuntimeError):
    pass


def normalize(text: str) -> str:
    bad_count = text.count(BAD)
    good_count = text.count(GOOD)
    if bad_count == 1 and good_count == 0:
        return text.replace(BAD, GOOD, 1)
    if bad_count == 0 and good_count == 1:
        return text
    raise CompatibilityError(
        "expected exactly one known malformed or normalized LRU Marie indent"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vmscan_source", type=Path)
    args = parser.parse_args()
    try:
        original = args.vmscan_source.read_text(encoding="utf-8")
        updated = normalize(original)
    except (OSError, UnicodeDecodeError, CompatibilityError) as exc:
        raise SystemExit(f"LRU Marie whitespace normalization failed: {exc}") from exc
    if updated != original:
        args.vmscan_source.write_text(updated, encoding="utf-8")
    print("LRU Marie vmscan continuation indentation normalized")


if __name__ == "__main__":
    main()
