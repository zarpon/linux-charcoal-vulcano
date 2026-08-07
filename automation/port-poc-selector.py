#!/usr/bin/env python3
"""Adapt a structurally verified POC patch to the Valve/BORE scheduler layout.

Native POC sources may place rq::poc_idle_committed next to either the older
rq::ttwu_pending area or, for the native 7.2 patch, the NO_HZ/UCLAMP area.
For native 7.2, the upstream patch is kept byte-for-byte unchanged after its
reviewed scheduler hunks are verified against the post-BORE source. Only
reviewed older layouts use the explicit ttwu_pending relocation and Valve
CONFIG_SMP compatibility context.
The resolver locks the exact source bytes, commit, path and SHA-256 for every
build; this adapter rejects unreviewed source shapes instead of silently using
a port intended for another kernel line.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

SECTION_HEADER = "diff --git a/kernel/sched/sched.h b/kernel/sched/sched.h\n"
FAIR_SECTION_HEADER = "diff --git a/kernel/sched/fair.c b/kernel/sched/fair.c\n"
EXPECTED_ADDITIONS = (
    "+#ifdef CONFIG_SCHED_POC_SELECTOR\n"
    "+\tunsigned int\t\tpoc_idle_committed;\n"
    "+#endif\n"
)
FIELD_BLOCK = EXPECTED_ADDITIONS
SCHED_ANCHOR_RE = re.compile(
    r"(?m)^(#ifdef CONFIG_SMP\n"
    r"\tunsigned int\t\tttwu_pending;\n"
    r"#endif\n"
    r"\tu64\t\t\tnr_switches;\n)"
)
TTWU_CONTEXT_RE = re.compile(r"(?m)^[ \t]*unsigned int[ \t]+ttwu_pending;[ \t]*\n")
NATIVE_72_NOHZ_CONTEXT_RE = re.compile(
    r"(?m)^ [ \t]*call_single_data_t[ \t]+nohz_csd;[ \t]*\n"
    r"^ #endif /\* CONFIG_NO_HZ_COMMON \*/[ \t]*\n"
)
NATIVE_72_UCLAMP_CONTEXT_RE = re.compile(r"(?m)^ #ifdef CONFIG_UCLAMP_TASK[ \t]*\n")
HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<context>.*\n)$"
)
IDLE_SIBLING_DECLARATION = (
    "static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu);\n"
)
IDLE_SIBLING_SYNC_DECLARATION = (
    "static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, int sync);\n"
)
PELT_INCLUDE = ' #include "pelt.h"\n'
VALVE_SMP_GUARD = " #ifdef CONFIG_SMP\n"


class PortError(RuntimeError):
    pass


def sched_section(text: str) -> str:
    start = text.find(SECTION_HEADER)
    if start < 0:
        raise PortError("POC patch does not contain kernel/sched/sched.h")
    end = text.find("\ndiff --git ", start + len(SECTION_HEADER))
    return text[start : len(text) if end < 0 else end]


def section_bounds(text: str, header: str, description: str) -> tuple[int, int]:
    start = text.find(header)
    if start < 0:
        raise PortError(f"POC patch does not contain {description}")
    end = text.find("\ndiff --git ", start + len(header))
    return start, len(text) if end < 0 else end


def next_hunk_end(text: str, hunk: int, section_end: int) -> int:
    next_hunk = text.find("\n@@ ", hunk + 1, section_end)
    return section_end if next_hunk < 0 else next_hunk + 1


def increment_hunk_context(header: str) -> str:
    match = HUNK_RE.match(header)
    if not match:
        raise PortError("select_idle_sibling hunk header changed upstream")
    old_count = int(match.group("old_count") or "1") + 1
    new_count = int(match.group("new_count") or "1") + 1
    return (
        f"@@ -{match.group('old_start')},{old_count} "
        f"+{match.group('new_start')},{new_count} @@{match.group('context')}"
    )


def old_hunk_text(body: str) -> str:
    lines: list[str] = []
    for line in body.splitlines(keepends=True):
        if line.startswith("+"):
            continue
        if line.startswith(("-", " ")):
            lines.append(line[1:])
            continue
        raise PortError("select_idle_sibling hunk has unsupported patch syntax")
    return "".join(lines)


def validate_hunk_context(body: str, source: str, description: str) -> None:
    old_text = old_hunk_text(body)
    source_offset = source.find(old_text)
    if source_offset < 0:
        raise PortError(f"{description} context does not match Valve/BORE source")
    if source.find(old_text, source_offset + 1) >= 0:
        raise PortError(f"{description} context is ambiguous in Valve/BORE source")


def rebase_hunk_header(header: str, body: str, fair_source: str) -> str:
    match = HUNK_RE.match(header)
    if not match:
        raise PortError("select_idle_sibling hunk header changed upstream")
    old_text = old_hunk_text(body)
    source_offset = fair_source.find(old_text)
    if source_offset < 0:
        raise PortError("select_idle_sibling context does not match Valve/BORE fair.c")
    if fair_source.find(old_text, source_offset + 1) >= 0:
        raise PortError("select_idle_sibling context is ambiguous in Valve/BORE fair.c")
    source_line = fair_source.count("\n", 0, source_offset) + 1
    old_start = int(match.group("old_start"))
    new_start = int(match.group("new_start"))
    return (
        f"@@ -{source_line},{match.group('old_count') or '1'} "
        f"+{source_line + new_start - old_start},{match.group('new_count') or '1'} "
        f"@@{match.group('context')}"
    )


def reviewed_idle_sibling_hunk(text: str) -> tuple[int, int, int, str]:
    fair_start, fair_end = section_bounds(text, FAIR_SECTION_HEADER, "kernel/sched/fair.c")
    candidate: tuple[int, int, int, str] | None = None
    hunk = text.find("@@ ", fair_start, fair_end)
    while hunk >= 0:
        header_end = text.find("\n", hunk, fair_end)
        if header_end < 0:
            raise PortError("select_idle_sibling hunk is malformed")
        header_end += 1
        hunk_end = next_hunk_end(text, hunk, fair_end)
        body = text[header_end:hunk_end]
        if (
            f"-{IDLE_SIBLING_DECLARATION}" in body
            and f"+{IDLE_SIBLING_SYNC_DECLARATION}" in body
        ):
            if candidate is not None:
                raise PortError("multiple select_idle_sibling hunks found upstream")
            candidate = (hunk, header_end, hunk_end, body)
        hunk = text.find("@@ ", hunk_end, fair_end)
    if candidate is None:
        raise PortError("reviewed select_idle_sibling hunk was not found")
    return candidate


def adapt_idle_sibling_hunk(text: str, fair_source: str | None = None) -> str:
    hunk, header_end, hunk_end, body = reviewed_idle_sibling_hunk(text)
    if body.count(PELT_INCLUDE) != 1:
        raise PortError("select_idle_sibling hunk no longer has one pelt.h anchor")
    if VALVE_SMP_GUARD in body:
        raise PortError("select_idle_sibling hunk already has a CONFIG_SMP guard")

    adapted_body = body.replace(PELT_INCLUDE, PELT_INCLUDE + VALVE_SMP_GUARD)
    if adapted_body == body:
        raise PortError("could not add the Valve CONFIG_SMP patch context")
    header = increment_hunk_context(text[hunk:header_end])
    if fair_source is not None:
        header = rebase_hunk_header(header, adapted_body, fair_source)
    return text[:hunk] + header + adapted_body + text[hunk_end:]


def sched_hunk(sched_header: str) -> str:
    if "poc_idle_committed" in sched_header:
        raise PortError("kernel/sched/sched.h already contains poc_idle_committed")
    matches = list(SCHED_ANCHOR_RE.finditer(sched_header))
    if len(matches) != 1:
        raise PortError(f"expected one Valve/BORE ttwu_pending anchor, found {len(matches)}")
    match = matches[0]
    line = sched_header.count("\n", 0, match.start()) + 1
    lines = match.group(1).splitlines(keepends=True)
    return (
        f"@@ -{line},4 +{line},7 @@ struct rq {{\n"
        + "".join(f" {item}" for item in lines[:2])
        + FIELD_BLOCK
        + "".join(f" {item}" for item in lines[2:])
    )


def insert_sched_hunk(text: str, header: str) -> str:
    section, section_end = section_bounds(text, SECTION_HEADER, "kernel/sched/sched.h")
    first_hunk = text.find("@@ ", section, section_end)
    if first_hunk < 0:
        raise PortError("POC patch has no remaining kernel/sched/sched.h hunk")
    return text[:first_hunk] + header + text[first_hunk:]


def is_native_72_sched_context(body: str) -> bool:
    return bool(
        NATIVE_72_NOHZ_CONTEXT_RE.search(body)
        and NATIVE_72_UCLAMP_CONTEXT_RE.search(body)
    )


def reviewed_sched_field_hunk(
    text: str, section_start: int, section_end: int
) -> tuple[int, int, str]:
    candidate: tuple[int, int, str] | None = None
    hunk = text.find("@@ ", section_start, section_end)
    while hunk >= 0:
        header_end = text.find("\n", hunk, section_end)
        if header_end < 0:
            raise PortError("rq::poc_idle_committed hunk is malformed")
        hunk_end = next_hunk_end(text, hunk, section_end)
        body = text[header_end + 1 : hunk_end]
        if EXPECTED_ADDITIONS in body:
            legacy_context = bool(TTWU_CONTEXT_RE.search(body))
            native_72_context = is_native_72_sched_context(body)
            if body.count("poc_idle_committed") != 1 or not (
                legacy_context or native_72_context
            ):
                raise PortError("rq::poc_idle_committed hunk changed upstream")
            if candidate is not None:
                raise PortError("multiple rq::poc_idle_committed hunks found upstream")
            candidate = (hunk, hunk_end, body)
        hunk = text.find("@@ ", hunk_end, section_end)
    if candidate is None:
        raise PortError("reviewed rq::poc_idle_committed hunk was not found")
    return candidate


def adapt_patch(
    text: str, fair_source: str | None = None, sched_header: str | None = None
) -> str:
    section, section_end = section_bounds(text, SECTION_HEADER, "kernel/sched/sched.h")
    hunk, next_hunk, body = reviewed_sched_field_hunk(text, section, section_end)

    if is_native_72_sched_context(body):
        # Native 7.2 POC already targets the Linux 7.2 scheduler layout.
        # BORE 6.8.0 does not alter either reviewed hunk. Validate both
        # original contexts against the post-BORE source and keep the patch
        # unchanged; git apply --check remains the authoritative full check.
        if sched_header is not None:
            validate_hunk_context(body, sched_header, "native 7.2 rq field")
        _, _, _, fair_body = reviewed_idle_sibling_hunk(text)
        if fair_source is not None:
            validate_hunk_context(
                fair_body, fair_source, "native 7.2 select_idle_sibling"
            )
        return text

    # Compatibility path for the reviewed older layout only. Those POC
    # variants placed the field next to ttwu_pending, which BORE/Valve could
    # move, so preserve the existing explicit relocation and CONFIG_SMP port.
    adapted = text[:hunk] + text[next_hunk:]
    adapted_sched = sched_section(adapted)
    if "poc_idle_committed" in adapted_sched:
        raise PortError("rq::poc_idle_committed hunk remains in sched.h")
    if sched_header is not None:
        adapted = insert_sched_hunk(adapted, sched_hunk(sched_header))
    return adapt_idle_sibling_hunk(adapted, fair_source)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--validate",
        action="store_true",
        help="validate the upstream hunk shape without writing an adapted patch",
    )
    parser.add_argument("patch", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("sched_header", type=Path, nargs="?")
    parser.add_argument("fair_source", type=Path, nargs="?")
    args = parser.parse_args()

    if args.validate:
        if args.output or args.sched_header or args.fair_source:
            parser.error("--validate accepts only the upstream patch path")
        try:
            adapt_patch(args.patch.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, PortError) as exc:
            raise SystemExit(f"POC Valve port failed: {exc}") from exc
        print(
            "POC Valve adapter accepted the current upstream hunk; "
            "the exact source bytes are recorded in patch-lock.json"
        )
        return

    if not args.output or not args.sched_header or not args.fair_source:
        parser.error("output, sched_header and fair_source are required unless --validate is used")

    try:
        adapted_patch = adapt_patch(
            args.patch.read_text(encoding="utf-8"),
            args.fair_source.read_text(encoding="utf-8"),
            args.sched_header.read_text(encoding="utf-8"),
        )
    except (UnicodeDecodeError, PortError) as exc:
        raise SystemExit(f"POC Valve port failed: {exc}") from exc

    args.output.write_text(adapted_patch, encoding="utf-8")
    print(
        "Prepared the locked upstream POC patch: native 7.2 kept unchanged "
        "after structural verification; legacy layouts explicitly ported"
    )


if __name__ == "__main__":
    main()
