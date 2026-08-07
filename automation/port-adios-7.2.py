#!/usr/bin/env python3
"""Explicitly port the locked ADIOS elevator hunk to Linux/Valve 7.2.

ADIOS 3.2.0 is available for multiple kernel generations.  The 7.2 resolver
prefers the newest compatible predecessor, while this adapter handles only the
elevator_set_default() layout difference between upstream Linux and Valve 7.2.
All non-elevator ADIOS hunks are preserved byte-for-byte.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path

ELEVATOR_DIFF = "diff --git a/block/elevator.c b/block/elevator.c\n"
TRAILER = "\n-- \n"
LEGACY_FUNC = "static struct elevator_type *elevator_get_default(struct request_queue *q)"
MODERN_FUNC = "void elevator_set_default(struct request_queue *q)"
LEGACY_ADIOS_GUARD = "+#ifdef CONFIG_MQ_IOSCHED_DEFAULT_ADIOS\n"
NAME_LINE = '\t\t.name = "mq-deadline",\n'
QUEUE_IF = (
    "\tif ((q->nr_hw_queues == 1 ||\n"
    "\t\t\tblk_mq_is_shared_tags(q->tag_set->flags))) {\n"
)


class PortError(RuntimeError):
    pass


def section_bounds(text: str) -> tuple[int, int]:
    start = text.find(ELEVATOR_DIFF)
    if start < 0:
        raise PortError("ADIOS patch does not contain block/elevator.c")
    next_diff = text.find("\ndiff --git ", start + len(ELEVATOR_DIFF))
    trailer = text.find(TRAILER, start + len(ELEVATOR_DIFF))
    candidates = [pos + 1 for pos in (next_diff, trailer) if pos >= 0]
    end = min(candidates) if candidates else len(text)
    return start, end


def validate_upstream_section(section: str) -> None:
    if LEGACY_FUNC in section:
        if section.count(LEGACY_ADIOS_GUARD) != 1:
            raise PortError("legacy ADIOS default guard shape changed upstream")
        if 'return elevator_find_get("adios");' not in section:
            raise PortError("legacy ADIOS elevator hunk no longer selects adios")
        return

    if MODERN_FUNC in section:
        if "CONFIG_MQ_IOSCHED_DEFAULT_ADIOS" not in section:
            raise PortError("modern ADIOS elevator hunk lost its default guard")
        if 'ctx.name = "adios";' not in section:
            raise PortError("modern ADIOS elevator hunk no longer selects adios")
        return

    raise PortError("ADIOS elevator hunk is not a reviewed legacy or modern layout")


def port_elevator_source(source: str) -> str:
    if MODERN_FUNC not in source:
        raise PortError("Linux/Valve 7.2 elevator_set_default() was not found")
    if source.count(NAME_LINE) != 1:
        raise PortError("expected one mq-deadline default name in 7.2 elevator.c")
    if source.count(QUEUE_IF) != 1:
        raise PortError("expected one 7.2 default-scheduler queue gate")
    if "CONFIG_MQ_IOSCHED_DEFAULT_ADIOS" in source:
        raise PortError("target elevator.c already contains the ADIOS 7.2 port")

    source = source.replace(
        NAME_LINE,
        "#ifdef CONFIG_MQ_IOSCHED_DEFAULT_ADIOS\n"
        '\t\t.name = "adios",\n'
        "#else\n"
        + NAME_LINE
        + "#endif\n",
        1,
    )
    source = source.replace(
        QUEUE_IF,
        "#ifdef CONFIG_MQ_IOSCHED_DEFAULT_ADIOS\n"
        "\t/* ADIOS is a multi-queue scheduler; preserve upstream ADIOS default semantics. */\n"
        "\tif (1) {\n"
        "#else\n"
        + QUEUE_IF
        + "#endif\n",
        1,
    )
    return source


def make_elevator_diff(original: str, ported: str) -> str:
    body = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            ported.splitlines(keepends=True),
            fromfile="a/block/elevator.c",
            tofile="b/block/elevator.c",
            n=3,
        )
    )
    if not body:
        raise PortError("ADIOS 7.2 elevator port produced no changes")
    return ELEVATOR_DIFF + body


def adapt_patch(patch: str, elevator_source: str) -> str:
    start, end = section_bounds(patch)
    validate_upstream_section(patch[start:end])
    ported = port_elevator_source(elevator_source)
    replacement = make_elevator_diff(elevator_source, ported)
    return patch[:start] + replacement + patch[end:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patch", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("elevator_source", type=Path)
    args = parser.parse_args()
    try:
        adapted = adapt_patch(
            args.patch.read_text(encoding="utf-8"),
            args.elevator_source.read_text(encoding="utf-8"),
        )
    except (OSError, UnicodeDecodeError, PortError) as exc:
        raise SystemExit(f"ADIOS 7.2 port failed: {exc}") from exc
    args.output.write_text(adapted, encoding="utf-8")
    print(
        "Prepared explicit ADIOS 3.2.0 -> Linux/Valve 7.2 elevator port; "
        "all non-elevator upstream hunks preserved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
