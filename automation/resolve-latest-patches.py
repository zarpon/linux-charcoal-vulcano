#!/usr/bin/env python3
"""Charcoal patch resolver wrapper enforcing newest-upstream adaptive ports."""
from __future__ import annotations

import difflib
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "resolve-latest-patches-base.py"

spec = importlib.util.spec_from_file_location("charcoal_resolver_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit(f"unable to load resolver base: {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

_ORIGINAL_RESOLVE_GITHUB_COMPONENT = base.resolve_github_component
ADIOS_VERSION = "3.3.0"

OLD_ELEVATOR = r'''void elevator_set_default(struct request_queue *q)
{
\tstruct elv_change_ctx ctx = {
\t\t.name = \"mq-deadline\",
\t\t.no_uevent = true,
\t};
\tint err;
\tstruct elevator_type *e;

\t/* now we allow to switch elevator */
\tblk_queue_flag_clear(QUEUE_FLAG_NO_ELV_SWITCH, q);

\tif (q->tag_set->flags & BLK_MQ_F_NO_SCHED_BY_DEFAULT)
\t\treturn;

\t/*
\t * For single queue devices, default to using mq-deadline. If we
\t * have multiple queues or mq-deadline is not available, default
\t * to \"none\".
\t */
\te = elevator_find_get(ctx.name);
\tif (!e)
\t\treturn;

\tif ((q->nr_hw_queues == 1 ||
\t\t\tblk_mq_is_shared_tags(q->tag_set->flags))) {
\t\terr = elevator_change(q, &ctx);
\t\tif (err < 0)
\t\t\tpr_warn(\"\\\"%s\\\" elevator initialization, failed %d, falling back to \\\"none\\\"\\n\",
\t\t\t\t\tctx.name, err);
\t}
\televator_put(e);
}
'''

NEW_ELEVATOR = r'''void elevator_set_default(struct request_queue *q)
{
\tstruct elv_change_ctx ctx = {
\t\t.name = \"mq-deadline\",
\t\t.no_uevent = true,
\t};
\tint err;
\tstruct elevator_type *e;

\t/* now we allow to switch elevator */
\tblk_queue_flag_clear(QUEUE_FLAG_NO_ELV_SWITCH, q);

\tif (q->tag_set->flags & BLK_MQ_F_NO_SCHED_BY_DEFAULT)
\t\treturn;

#ifdef CONFIG_MQ_IOSCHED_DEFAULT_ADIOS
\tctx.name = \"adios\";
#else
\tif (q->nr_hw_queues != 1 &&
\t    !blk_mq_is_shared_tags(q->tag_set->flags))
\t\treturn;
#endif

\t/*
\t * For single queue devices, default to using mq-deadline. If we
\t * have multiple queues or mq-deadline is not available, default
\t * to \"none\".
\t */
\te = elevator_find_get(ctx.name);
\tif (!e)
\t\treturn;

\terr = elevator_change(q, &ctx);
\tif (err < 0)
\t\tpr_warn(\"\\\"%s\\\" elevator initialization, failed %d, falling back to \\\"none\\\"\\n\",
\t\t\t\tctx.name, err);
\televator_put(e);
}
'''


def _decode_c_template(text: str) -> str:
    """Decode one Python-source escaping layer while preserving C escapes.

    The raw template uses ``\\t`` for source indentation, ``\\\"`` for ordinary
    C quotes and ``\\\\\"``/``\\\\n`` for C string escapes.  unicode_escape
    removes exactly that outer representation layer, yielding the byte-for-byte
    C source text used by the Valve 6.16 tree.
    """
    return text.encode("utf-8").decode("unicode_escape")


OLD_ELEVATOR = _decode_c_template(OLD_ELEVATOR)
NEW_ELEVATOR = _decode_c_template(NEW_ELEVATOR)


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise base.ResolveError(
            f"ADIOS {ADIOS_VERSION} port: {label} expected once, found {count}"
        )
    return text.replace(old, new, 1)


def _recount_new_file_hunk(text: str) -> str:
    marker = "diff --git a/block/adios.c b/block/adios.c\n"
    start = text.find(marker)
    if start < 0:
        raise base.ResolveError("ADIOS port: block/adios.c diff is missing")
    next_diff = text.find("\ndiff --git ", start + len(marker))
    end = len(text) if next_diff < 0 else next_diff + 1
    block = text[start:end]
    lines = block.splitlines()
    hunk_index = next((i for i, line in enumerate(lines) if line.startswith("@@ -0,0 +1,")), -1)
    if hunk_index < 0:
        raise base.ResolveError("ADIOS port: new-file hunk header is missing")
    added = sum(
        1 for line in lines[hunk_index + 1 :]
        if line.startswith("+") and not line.startswith("+++")
    )
    lines[hunk_index] = re.sub(
        r"@@ -0,0 \+1,\d+ @@", f"@@ -0,0 +1,{added} @@", lines[hunk_index], count=1
    )
    replacement = "\n".join(lines) + ("\n" if block.endswith("\n") else "")
    return text[:start] + replacement + text[end:]


def port_adios_616(data: bytes) -> bytes:
    text = data.decode("utf-8")
    version_match = re.search(r'^\+#define ADIOS_VERSION "([^"]+)"$', text, re.MULTILINE)
    if not version_match:
        raise base.ResolveError("ADIOS adaptive port: upstream version marker is missing")
    version = version_match.group(1)
    if version != ADIOS_VERSION:
        raise base.ResolveError(
            f"ADIOS adaptive porter supports {ADIOS_VERSION}, newest upstream is {version}; "
            "refresh the port instead of using an older patch"
        )

    elevator_at = text.find("\ndiff --git a/block/elevator.c b/block/elevator.c\n")
    if elevator_at < 0:
        raise base.ResolveError("ADIOS adaptive port: upstream elevator diff is missing")
    text = text[: elevator_at + 1]

    limit_anchor = "+// We limit the depth of request allocation for asynchronous and write requests\n"
    helper = '''+// Convert queue depth to the 6.16 word-depth representation used by sbitmap.
+static int to_word_depth(struct blk_mq_hw_ctx *hctx, unsigned int qdepth) {
+\tstruct sbitmap_queue *bt = &hctx->sched_tags->bitmap_tags;
+\tconst unsigned int nrr = hctx->queue->nr_requests;
+
+\treturn ((qdepth << bt->sb.shift) + nrr - 1) / nrr;
+}
+
'''
    text = replace_exact(text, limit_anchor, helper + limit_anchor, "word-depth insertion")
    text = replace_exact(
        text,
        "+\tdata->shallow_depth = ad->async_depth;\n",
        "+\tdata->shallow_depth = to_word_depth(data->hctx, ad->async_depth);\n",
        "limit-depth conversion",
    )

    old_depth = '''+static void adios_depth_updated(struct request_queue *q) {
+\tstruct adios_data *ad = q->elevator->elevator_data;
+
+\tad->async_depth = q->nr_requests;
+\tblk_mq_set_min_shallow_depth(q, ad->async_depth);
+}
'''
    new_depth = '''+static void adios_depth_updated(struct blk_mq_hw_ctx *hctx) {
+\tstruct request_queue *q = hctx->queue;
+\tstruct adios_data *ad = q->elevator->elevator_data;
+\tstruct blk_mq_tags *tags = hctx->sched_tags;
+\tad->async_depth = q->nr_requests;
+\tsbitmap_queue_min_shallow_depth(&tags->bitmap_tags, 1);
+}
'''
    text = replace_exact(text, old_depth, new_depth, "depth-updated API")

    init_anchor = "+// Initialize the scheduler-specific data when initializing the request queue\n"
    init_hctx = '''+// Initialize the 6.16 per-hardware-queue shallow-depth state.
+static int adios_init_hctx(struct blk_mq_hw_ctx *hctx, unsigned int hctx_idx) {
+\tadios_depth_updated(hctx);
+\treturn 0;
+}
+
'''
    text = replace_exact(text, init_anchor, init_hctx + init_anchor, "init_hctx insertion")
    text = replace_exact(
        text,
        "+\tadios_depth_updated(q);\n",
        "",
        "queue-level depth initialization removal",
    )
    text = replace_exact(
        text,
        "+\t\t.init_sched\t\t\t= adios_init_sched,\n",
        "+\t\t.init_hctx\t\t\t= adios_init_hctx,\n"
        "+\t\t.init_sched\t\t\t= adios_init_sched,\n",
        "init_hctx ops registration",
    )
    text = _recount_new_file_hunk(text)

    elevator_diff = list(
        difflib.unified_diff(
            OLD_ELEVATOR.splitlines(keepends=True),
            NEW_ELEVATOR.splitlines(keepends=True),
            fromfile="a/block/elevator.c",
            tofile="b/block/elevator.c",
            n=6,
        )
    )
    if not elevator_diff:
        raise base.ResolveError("ADIOS adaptive port: elevator diff generation failed")
    text += "diff --git a/block/elevator.c b/block/elevator.c\n" + "".join(elevator_diff)

    encoded = text.encode("utf-8")
    if b'ADIOS_VERSION "3.3.0"' not in encoded:
        raise base.ResolveError("ADIOS adaptive port lost the 3.3.0 version marker")
    for marker in (
        b"to_word_depth",
        b"sbitmap_queue_min_shallow_depth",
        b"adios_init_hctx",
        b'ctx.name = "adios"',
    ):
        if marker not in encoded:
            raise base.ResolveError(f"ADIOS adaptive port lost marker {marker!r}")
    return encoded


def resolve_github_component(
    component: dict[str, Any], kernel_version: str, token: str | None, root: Path
) -> dict[str, Any]:
    item = _ORIGINAL_RESOLVE_GITHUB_COMPONENT(component, kernel_version, token, root)
    if item.get("origin") == "adaptive-port" and item.get("adapter") == "adios-valve-616":
        if kernel_version != "6.16.12":
            raise base.ResolveError(
                f"ADIOS Valve 6.16 porter invoked for unsupported kernel {kernel_version}"
            )
        item["content_bytes"] = port_adios_616(item["content_bytes"])
        item["adapter"] = "adios-valve-616"
        item["port_for_kernel"] = kernel_version
    return item


base.resolve_github_component = resolve_github_component
for name in dir(base):
    if not name.startswith("__"):
        globals().setdefault(name, getattr(base, name))
globals()["resolve_github_component"] = resolve_github_component


if __name__ == "__main__":
    raise SystemExit(base.main())
