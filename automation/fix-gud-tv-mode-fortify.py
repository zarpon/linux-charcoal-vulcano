#!/usr/bin/env python3
"""Keep GUD TV-mode buffers bounded and visible to O3/Full-LTO FORTIFY."""
from __future__ import annotations

import argparse
from pathlib import Path

SIGNATURE = (
    "static int gud_connector_add_tv_mode(struct gud_device *gdrm, "
    "struct drm_connector *connector)\n{\n"
)
REPLACEMENTS = (
    ("\tchar *buf;", "\tchar (*buf)[GUD_CONNECTOR_TV_MODE_NAME_LEN];"),
    (
        "\tbuf = kmalloc(buf_len, GFP_KERNEL);",
        "\tbuf = kmalloc_array(GUD_CONNECTOR_TV_MODE_MAX_NUM, sizeof(*buf), GFP_KERNEL);",
    ),
    (
        "\tif (!ret || ret % GUD_CONNECTOR_TV_MODE_NAME_LEN) {",
        "\tif (!ret || ret > buf_len || ret % GUD_CONNECTOR_TV_MODE_NAME_LEN) {",
    ),
    (
        "\tnum_modes = ret / GUD_CONNECTOR_TV_MODE_NAME_LEN;",
        "\tnum_modes = ret / sizeof(*buf);",
    ),
    (
        "\t\tchar *mode = &buf[i * GUD_CONNECTOR_TV_MODE_NAME_LEN];",
        "\t\tchar *mode = buf[i];",
    ),
    (
        "\t\tif (!memchr(mode, '\\0', GUD_CONNECTOR_TV_MODE_NAME_LEN)) {",
        "\t\tif (!memchr(mode, '\\0', sizeof(*buf))) {",
    ),
)


class CompatibilityError(RuntimeError):
    pass


def adapt(text: str) -> str:
    if text.count(SIGNATURE) != 1:
        raise CompatibilityError("expected one GUD TV-mode function")
    start = text.index(SIGNATURE)
    end = text.find("\n}\n", start)
    if end == -1:
        raise CompatibilityError("GUD TV-mode function boundary changed")
    end += len("\n}\n")
    block = text[start:end]
    for old, new in REPLACEMENTS:
        if block.count(new) == 1 and old not in block:
            continue
        if block.count(old) != 1 or new in block:
            raise CompatibilityError(f"GUD TV-mode source anchor changed: {old.strip()}")
        block = block.replace(old, new, 1)
    return text[:start] + block + text[end:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("connector_source", type=Path)
    args = parser.parse_args()
    try:
        original = args.connector_source.read_text(encoding="utf-8")
        updated = adapt(original)
    except (OSError, UnicodeDecodeError, CompatibilityError) as exc:
        raise SystemExit(f"GUD TV-mode FORTIFY fix failed: {exc}") from exc
    if updated != original:
        args.connector_source.write_text(updated, encoding="utf-8")
    print("GUD TV-mode response: bounded typed slots for O3/Full LTO/FORTIFY")


if __name__ == "__main__":
    main()
