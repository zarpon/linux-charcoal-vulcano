#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


class ChecksumError(RuntimeError):
    pass


def array_bounds(text: str, variable: str) -> tuple[int, int]:
    start = re.search(rf"(?m)^{re.escape(variable)}=\(", text)
    if not start:
        raise ChecksumError(f"{variable} array not found")
    end = re.search(r"(?m)^\s*\)\s*$", text[start.end():])
    if not end:
        raise ChecksumError(f"unterminated {variable} array")
    return start.start(), start.end() + end.end()


def values(block: str) -> list[str]:
    return re.findall(r"['\"]([^'\"]+)['\"]", block)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pkgbuild", default="PKGBUILD")
    parser.add_argument("--generated", required=True)
    parser.add_argument("--report", default="logs/checksum-validation.txt")
    args = parser.parse_args()

    pkgbuild_path = Path(args.pkgbuild)
    text = pkgbuild_path.read_text(encoding="utf-8")
    generated = Path(args.generated).read_text(encoding="utf-8").strip()
    if not generated.startswith("sha256sums=("):
        raise ChecksumError("makepkg did not generate a sha256sums array")

    source_start, source_end = array_bounds(text, "source")
    generated_start, generated_end = array_bounds(generated, "sha256sums")
    sources = values(text[source_start:source_end])
    checksums = values(generated[generated_start:generated_end])
    if len(sources) != len(checksums):
        raise ChecksumError(
            f"source/checksum count mismatch: {len(sources)} sources, {len(checksums)} checksums"
        )

    vcs_indexes = [
        index for index, source in enumerate(sources)
        if "git+" in source or source.startswith(("git://", "svn+", "hg+", "bzr+"))
    ]
    invalid: list[str] = []
    skip_indexes: list[int] = []
    for index, checksum in enumerate(checksums):
        if checksum == "SKIP":
            skip_indexes.append(index)
            if index not in vcs_indexes:
                invalid.append(f"non-VCS source uses SKIP: {sources[index]}")
        elif not re.fullmatch(r"[0-9a-f]{64}", checksum):
            invalid.append(f"invalid SHA-256 for {sources[index]}: {checksum}")

    if invalid:
        raise ChecksumError("; ".join(invalid))

    sha_start, sha_end = array_bounds(text, "sha256sums")
    replacement = generated[generated_start:generated_end]
    pkgbuild_path.write_text(text[:sha_start] + replacement + text[sha_end:], encoding="utf-8")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"sources={len(sources)}",
        f"sha256={len(checksums) - len(skip_indexes)}",
        f"vcs_skip={len(skip_indexes)}",
    ]
    lines.extend(f"vcs_skip_source={sources[index]}" for index in skip_indexes)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ChecksumError as exc:
        print(f"checksum error: {exc}")
        raise SystemExit(2)
