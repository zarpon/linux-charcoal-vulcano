#!/usr/bin/env python3
"""Make the upstream libbpf GCC warning workaround safe for Clang builds."""
from __future__ import annotations

import argparse
from pathlib import Path

PRAGMA = '#pragma GCC diagnostic ignored "-Wmaybe-uninitialized"'
GUARDED = (
    "#if !defined(__clang__)\n"
    f"{PRAGMA}\n"
    "#endif /* !__clang__ */"
)
EXPECTED_OCCURRENCES = 1


class CompatibilityError(RuntimeError):
    pass


def adapt(text: str) -> str:
    if GUARDED in text:
        raise CompatibilityError("libbpf Clang warning guard is already present")
    count = text.count(PRAGMA)
    if count != EXPECTED_OCCURRENCES:
        raise CompatibilityError(
            f"expected {EXPECTED_OCCURRENCES} GCC warning pragma, found {count}"
        )
    adapted = text.replace(PRAGMA, GUARDED)
    if adapted.count(GUARDED) != EXPECTED_OCCURRENCES:
        raise CompatibilityError("failed to guard the GCC warning pragma")
    return adapted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("elf_source", type=Path)
    args = parser.parse_args()

    try:
        source = args.elf_source.read_text(encoding="utf-8")
        adapted = adapt(source)
    except (OSError, UnicodeDecodeError, CompatibilityError) as exc:
        raise SystemExit(f"libbpf Clang compatibility fix failed: {exc}") from exc

    args.elf_source.write_text(adapted, encoding="utf-8")
    print("Guarded the GCC-only -Wmaybe-uninitialized pragma from Clang")


if __name__ == "__main__":
    main()
