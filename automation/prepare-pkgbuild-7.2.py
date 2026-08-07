#!/usr/bin/env python3
"""Transform the production PKGBUILD into the isolated SteamOS 7.2 variant."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BOOTSTRAP_TAG = "7.2.0-rc3-valve-beta1"
PATCH_ORDER = [
    "latest-bore.patch",
    "latest-bore-sched-ext-coexistence-fix.patch",
    "latest-poc-selector.patch",
    "latest-adios.patch",
    "latest-adios-default.patch",
]
UPSTREAMED_72_PATCHES = {
    "latest-c23-libbpf.patch": (
        "upstream commit d70f79fef65810faf64dbae1f3a1b5623cdb2345 "
        "is already present in Valve 7.2"
    ),
}


class TransformError(RuntimeError):
    pass


def replace_assignment(text: str, name: str, value: str) -> str:
    updated, count = re.subn(
        rf"(?m)^{re.escape(name)}=.*$", f"{name}={value}", text, count=1
    )
    if count != 1:
        raise TransformError(f"assignment not found: {name}")
    return updated


def array_bounds(text: str, name: str) -> tuple[int, int]:
    start_match = re.search(rf"(?m)^{re.escape(name)}=\(\s*$", text)
    if not start_match:
        raise TransformError(f"array not found: {name}")
    end_match = re.search(r"(?m)^\)\s*$", text[start_match.end() :])
    if not end_match:
        raise TransformError(f"unterminated array: {name}")
    return start_match.start(), start_match.end() + end_match.end()


def normalized(line: str) -> str:
    value = line.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def reorder_patches(text: str) -> str:
    start, end = array_bounds(text, "source")
    block = text[start:end]
    lines = block.splitlines(keepends=True)
    found: dict[str, str] = {}
    retained: list[str] = []
    for line in lines:
        value = normalized(line)
        if value in PATCH_ORDER:
            if value in found:
                raise TransformError(f"duplicate patch source: {value}")
            found[value] = line
        else:
            retained.append(line)
    missing = [name for name in PATCH_ORDER if name not in found]
    if missing:
        raise TransformError(f"missing patch sources: {', '.join(missing)}")

    # Insert the mandatory scheduler stack immediately before the first Zen
    # patch. This preserves all unrelated source ordering.
    insert_at = next(
        (
            index
            for index, line in enumerate(retained)
            if normalized(line) == "latest-zen-01.patch"
        ),
        len(retained) - 1,
    )
    ordered = [found[name] for name in PATCH_ORDER]
    retained[insert_at:insert_at] = ordered
    return text[:start] + "".join(retained) + text[end:]


def skip_upstreamed_72_patches(text: str) -> str:
    """Skip patches proven to be already integrated in the Valve 7.2 tree.

    Keep them in source()/sha256sums so the resolver and checksum lock continue
    to verify their exact upstream provenance. Only their application is skipped.
    """
    if "Valve 7.2 already contains the upstream change" in text:
        return text

    pattern = (
        r"(?m)^(?P<indent>\s*)if \[\[ \$src == "
        r"latest-poc-selector\.patch \]\]; then"
    )
    match = re.search(pattern, text)
    if not match:
        raise TransformError("prepare() patch dispatcher not found")

    indent = match.group("indent")
    names = " ".join(UPSTREAMED_72_PATCHES)
    replacement = (
        f'{indent}if [[ " {names} " == *" $src "* ]]; then\n'
        f'{indent}  echo "Skipping $src: Valve 7.2 already contains the upstream change."\n'
        f"{indent}  continue\n"
        f"{indent}elif [[ $src == latest-poc-selector.patch ]]; then"
    )
    return re.sub(pattern, replacement, text, count=1)


def transform(text: str) -> str:
    text = replace_assignment(text, "pkgbase", "linux-charcoal-72")
    text = replace_assignment(text, "_nepbase", "linux-neptune-72")
    text = replace_assignment(text, "_tag", BOOTSTRAP_TAG)
    text = reorder_patches(text)
    text = skip_upstreamed_72_patches(text)
    return text


def validate(text: str) -> None:
    required = {
        "pkgbase=linux-charcoal-72",
        "_nepbase=linux-neptune-72",
        f"_tag={BOOTSTRAP_TAG}",
    }
    for value in required:
        if value not in text:
            raise TransformError(f"missing transformed value: {value}")
    positions = [text.index(name) for name in PATCH_ORDER]
    if positions != sorted(positions):
        raise TransformError("mandatory patch order is invalid")
    if text.count("latest-poc-selector.patch") != 2:
        # one source entry and one prepare() special case
        raise TransformError("unexpected POC selector reference count")
    for patch in UPSTREAMED_72_PATCHES:
        if patch not in text:
            raise TransformError(f"upstreamed 7.2 patch source disappeared: {patch}")
    if "Valve 7.2 already contains the upstream change" not in text:
        raise TransformError("missing Valve 7.2 upstreamed-patch guard")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="PKGBUILD")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    path = Path(args.path)
    updated = transform(path.read_text(encoding="utf-8"))
    validate(updated)
    if args.write:
        path.write_text(updated, encoding="utf-8")
    else:
        sys.stdout.write(updated)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TransformError) as exc:
        print(f"PKGBUILD 7.2 transformation error: {exc}", file=sys.stderr)
        raise SystemExit(2)
