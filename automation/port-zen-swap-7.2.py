#!/usr/bin/env python3
"""Apply the locked Zen swap readahead change to Valve 7.2 layouts."""
from __future__ import annotations

import argparse
from pathlib import Path

SWAP_DIFF = "diff --git a/mm/swap.c b/mm/swap.c"
INIT_DIFF = "diff --git a/init/Kconfig b/init/Kconfig"
ZEN_GUARD = "+#ifdef CONFIG_ZEN_INTERACTIVE"
ZEN_ASSIGN = "+\tpage_cluster = 0;"
ZEN_HELP = "+\t    Swap-in readahead..............:   3    ->   0"
HELP_LINE = "\t    Swap-in readahead..............:   3    ->   0\n"
HELP_ANCHOR = "\t    Watermark boost factor.........:   1.5  ->   0\n"
FUNC = "void __init swap_setup(void)\n{\n"
REGISTER = '\tregister_sysctl_init("vm", swap_sysctl_table);\n'


class PortError(RuntimeError):
    pass


def validate_patch(patch: str) -> None:
    if SWAP_DIFF not in patch or INIT_DIFF not in patch:
        raise PortError(
            "Zen swap patch no longer contains the reviewed init/Kconfig and mm/swap.c changes"
        )
    if patch.count(ZEN_GUARD) != 1:
        raise PortError(
            "Zen swap patch no longer adds exactly one CONFIG_ZEN_INTERACTIVE guard"
        )
    if patch.count(ZEN_ASSIGN) != 1:
        raise PortError(
            "Zen swap patch no longer sets page_cluster to zero exactly once"
        )
    if patch.count(ZEN_HELP) != 1:
        raise PortError(
            "Zen swap patch no longer adds the reviewed ZEN_INTERACTIVE help line exactly once"
        )
    if "config ZEN_INTERACTIVE" not in patch:
        raise PortError(
            "Zen swap patch no longer updates the ZEN_INTERACTIVE help text"
        )


def adapt_swap_source(source: str) -> str:
    if source.count(FUNC) != 1:
        raise PortError("expected exactly one Valve 7.2 swap_setup()")
    if source.count(REGISTER) != 1:
        raise PortError(
            "expected exactly one vm sysctl registration in Valve 7.2 swap.c"
        )
    if (
        "#ifdef CONFIG_ZEN_INTERACTIVE\n"
        "\t/* Only swap-in pages requested, avoid readahead */"
    ) in source:
        raise PortError("target swap.c already contains the Zen 7.2 port")

    func_start = source.index(FUNC) + len(FUNC)
    register_at = source.index(REGISTER, func_start)
    middle = source[func_start:register_at]
    if "page_cluster" not in middle:
        raise PortError(
            "Valve 7.2 swap_setup() no longer configures page_cluster"
        )

    replacement = (
        "#ifdef CONFIG_ZEN_INTERACTIVE\n"
        "\t/* Only swap-in pages requested, avoid readahead */\n"
        "\tpage_cluster = 0;\n"
        "#else\n"
        + middle
        + "#endif\n\n"
    )
    return source[:func_start] + replacement + source[register_at:]


def adapt_kconfig(source: str) -> str:
    if source.count("config ZEN_INTERACTIVE\n") != 1:
        raise PortError("expected exactly one CONFIG_ZEN_INTERACTIVE stanza")
    if HELP_LINE in source:
        raise PortError("target init/Kconfig already contains the Zen swap help line")

    stanza_start = source.index("config ZEN_INTERACTIVE\n")
    next_config = source.find("\nconfig ", stanza_start + 1)
    stanza_end = len(source) if next_config < 0 else next_config + 1
    stanza = source[stanza_start:stanza_end]
    if stanza.count(HELP_ANCHOR) != 1:
        raise PortError(
            "CONFIG_ZEN_INTERACTIVE no longer contains the reviewed watermark help anchor"
        )

    stanza = stanza.replace(HELP_ANCHOR, HELP_ANCHOR + HELP_LINE, 1)
    return source[:stanza_start] + stanza + source[stanza_end:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patch", type=Path)
    parser.add_argument("swap_target", type=Path)
    parser.add_argument("kconfig_target", type=Path)
    args = parser.parse_args()
    try:
        patch = args.patch.read_text(encoding="utf-8")
        swap_source = args.swap_target.read_text(encoding="utf-8")
        kconfig_source = args.kconfig_target.read_text(encoding="utf-8")
        validate_patch(patch)
        adapted_swap = adapt_swap_source(swap_source)
        adapted_kconfig = adapt_kconfig(kconfig_source)
    except (OSError, UnicodeDecodeError, PortError) as exc:
        raise SystemExit(f"Zen swap 7.2 port failed: {exc}") from exc

    args.swap_target.write_text(adapted_swap, encoding="utf-8")
    args.kconfig_target.write_text(adapted_kconfig, encoding="utf-8")
    print(
        "Applied explicit Zen e3afdec port for Valve 7.2: disabled swap-in "
        "readahead and updated ZEN_INTERACTIVE help text"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
