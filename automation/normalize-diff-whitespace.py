#!/usr/bin/env python3
"""Normalize only whitespace errors reported by git diff --check.

The 7.2 patch stack intentionally tracks exact newest-upstream patch bytes in
patch-lock.json. Some upstream patches contain style-only whitespace defects.
This helper keeps the upstream lock intact and repairs only changed lines that
git itself reports, after patch application and before the mandatory clean
git diff --check. Unsupported diagnostics fail closed.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

DIAGNOSTIC = re.compile(
    r"^(?P<path>.+):(?P<line>[0-9]+): "
    r"(?P<kind>trailing whitespace|space before tab in indent)\.$"
)
ALLOWED_KINDS = {"trailing whitespace", "space before tab in indent"}


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
        raise NormalizeError(
            "space-before-tab diagnostic has no leading whitespace"
        )
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


def normalize(root: Path) -> int:
    before = run_diff_check(root)
    if before.returncode == 0:
        print("git diff --check already clean; no normalization required")
        return 0

    diagnostics = parse_diagnostics(before.stdout + before.stderr)
    if not diagnostics:
        raise NormalizeError(
            "git diff --check failed without supported whitespace diagnostics"
        )

    grouped: dict[tuple[str, int], set[str]] = {}
    for path, line_no, kind in diagnostics:
        grouped.setdefault((path, line_no), set()).add(kind)

    touched: set[str] = set()
    for (relative, line_no), kinds in sorted(grouped.items()):
        path = root / relative
        if not path.is_file():
            raise NormalizeError(f"reported file is missing: {relative}")
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if line_no < 1 or line_no > len(lines):
            raise NormalizeError(
                f"reported line is out of range: {relative}:{line_no}"
            )
        old = lines[line_no - 1]
        new = normalize_line(old, kinds)
        if new == old:
            raise NormalizeError(
                "diagnostic could not be normalized without broader edits: "
                f"{relative}:{line_no}"
            )
        lines[line_no - 1] = new
        path.write_text("".join(lines), encoding="utf-8", newline="")
        touched.add(relative)
        print(
            f"normalized {relative}:{line_no}: "
            + ", ".join(sorted(kinds))
        )

    after = run_diff_check(root)
    if after.returncode != 0:
        raise NormalizeError(
            "git diff --check remains dirty after targeted normalization:\n"
            + after.stdout
            + after.stderr
        )
    print(
        "git diff --check clean after targeted normalization of "
        f"{len(grouped)} line(s) in {len(touched)} file(s)"
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
