#!/usr/bin/env python3
"""Normalize only whitespace errors reported by git diff --check.

The 7.2 patch stack keeps exact newest-upstream patch bytes in patch-lock.json.
Some upstream patches contain style-only whitespace defects. This helper runs
after patch application and repairs only the exact changed lines diagnosed by
git diff --check. Unsupported diagnostics fail closed, and a clean diff check
is mandatory after normalization.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

DIAGNOSTIC = re.compile(
    r"^(?P<path>.+):(?P<line>[0-9]+): "
    r"(?P<kind>trailing whitespace|space before tab in indent|new blank line at EOF)\.$"
)
ALLOWED_KINDS = {
    "trailing whitespace",
    "space before tab in indent",
    "new blank line at EOF",
}


class NormalizeError(RuntimeError):
    pass


def run_diff_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "diff", "--check", "--no-color"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_diagnostics(output: str) -> list[tuple[str, int, str]]:
    diagnostics: list[tuple[str, int, str]] = []
    unexplained: list[str] = []
    for raw in output.splitlines():
        if not raw.strip() or raw.startswith("+"):
            continue
        match = DIAGNOSTIC.fullmatch(raw)
        if not match:
            unexplained.append(raw)
            continue
        kind = match.group("kind")
        if kind not in ALLOWED_KINDS:
            unexplained.append(raw)
            continue
        diagnostics.append((match.group("path"), int(match.group("line")), kind))
    if unexplained:
        raise NormalizeError(
            "git diff --check reported unsupported diagnostics: "
            + " | ".join(unexplained)
        )
    return diagnostics


def split_newline(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def normalize_indent(body: str) -> str:
    match = re.match(r"^[ \t]+", body)
    if not match:
        raise NormalizeError("space-before-tab diagnostic has no leading whitespace")
    prefix = match.group(0)
    width = len(prefix.expandtabs(8))
    normalized = "\t" * (width // 8) + " " * (width % 8)
    return normalized + body[len(prefix):]


def normalize_line(line: str, kinds: set[str]) -> str:
    body, newline = split_newline(line)
    if "space before tab in indent" in kinds:
        body = normalize_indent(body)
    if "trailing whitespace" in kinds:
        body = body.rstrip(" \t")
    return body + newline


def trim_blank_eof(path: Path, first_blank_line: int) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if first_blank_line < 1 or first_blank_line > len(lines):
        raise NormalizeError(f"EOF diagnostic line is out of range: {path}:{first_blank_line}")
    suffix = lines[first_blank_line - 1 :]
    if not suffix or any(line.strip(" \t\r\n") for line in suffix):
        raise NormalizeError(
            f"EOF diagnostic does not point to an all-blank suffix: {path}:{first_blank_line}"
        )
    path.write_text("".join(lines[: first_blank_line - 1]), encoding="utf-8", newline="")


def normalize(root: Path) -> int:
    before = run_diff_check(root)
    if before.returncode == 0:
        print("git diff --check already clean; no normalization required", flush=True)
        return 0

    raw = before.stdout + before.stderr
    print("initial git diff --check diagnostics:", flush=True)
    print(raw, end="" if raw.endswith("\n") else "\n", flush=True)
    diagnostics = parse_diagnostics(raw)
    if not diagnostics:
        raise NormalizeError("git diff --check failed without supported whitespace diagnostics")

    grouped: dict[tuple[str, int], set[str]] = {}
    for path, line_no, kind in diagnostics:
        grouped.setdefault((path, line_no), set()).add(kind)

    eof_by_path: dict[str, int] = {}
    normal: dict[tuple[str, int], set[str]] = {}
    for key, kinds in grouped.items():
        relative, line_no = key
        if "new blank line at EOF" in kinds:
            eof_by_path[relative] = min(eof_by_path.get(relative, line_no), line_no)
            kinds = kinds - {"new blank line at EOF"}
        if kinds:
            normal[key] = kinds

    touched: set[str] = set()
    for (relative, line_no), kinds in sorted(normal.items()):
        path = root / relative
        if not path.is_file():
            raise NormalizeError(f"reported file is missing: {relative}")
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if line_no < 1 or line_no > len(lines):
            raise NormalizeError(f"reported line is out of range: {relative}:{line_no}")
        old = lines[line_no - 1]
        new = normalize_line(old, kinds)
        if new == old:
            raise NormalizeError(
                f"diagnostic could not be normalized without broader edits: {relative}:{line_no}"
            )
        lines[line_no - 1] = new
        path.write_text("".join(lines), encoding="utf-8", newline="")
        touched.add(relative)
        print(f"normalized {relative}:{line_no}: " + ", ".join(sorted(kinds)), flush=True)

    for relative, line_no in sorted(eof_by_path.items()):
        path = root / relative
        if not path.is_file():
            raise NormalizeError(f"reported file is missing: {relative}")
        trim_blank_eof(path, line_no)
        touched.add(relative)
        print(f"normalized {relative}:{line_no}: new blank line at EOF", flush=True)

    after = run_diff_check(root)
    if after.returncode != 0:
        raise NormalizeError(
            "git diff --check remains dirty after targeted normalization:\n"
            + after.stdout + after.stderr
        )
    print(
        "git diff --check clean after targeted normalization of "
        f"{len(grouped)} diagnostic line(s) in {len(touched)} file(s)",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / ".git").exists():
        raise NormalizeError(f"not a git work tree root: {root}")
    return normalize(root)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NormalizeError as exc:
        raise SystemExit(f"whitespace normalization failed: {exc}") from exc
