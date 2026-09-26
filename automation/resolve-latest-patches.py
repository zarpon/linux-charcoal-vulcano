#!/usr/bin/env python3
"""Charcoal patch resolver wrapper enforcing newest-upstream adaptive ports."""
from __future__ import annotations

import importlib.util
import hashlib
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
ADIOS_SOURCE_REVISION = "3.3.0r2"

# Valve 6.16.12-specific compatibility scaffold for elevator_set_default().
# This is the exact target-side hunk shape already validated against the
# SteamOS 6.16 Valve tree. It does not pin ADIOS to an older release: the
# scheduler implementation below still comes from the newest upstream 3.3.0r2
# patch and the version/hash checks deliberately fail when upstream advances.
ELEVATOR_PATCH_616 = '''diff --git a/block/elevator.c b/block/elevator.c
--- a/block/elevator.c
+++ b/block/elevator.c
@@ -752,6 +752,14 @@ void elevator_set_default(struct request_queue *q)
 \tif (q->tag_set->flags & BLK_MQ_F_NO_SCHED_BY_DEFAULT)
 \t\treturn;
 
+#ifdef CONFIG_MQ_IOSCHED_DEFAULT_ADIOS
+\tctx.name = "adios";
+#else
+\tif (q->nr_hw_queues != 1 &&
+\t    !blk_mq_is_shared_tags(q->tag_set->flags))
+\t\treturn;
+#endif
+
 \t/*
 \t * For single queue devices, default to using mq-deadline. If we
 \t * have multiple queues or mq-deadline is not available, default
@@ -761,12 +769,9 @@ void elevator_set_default(struct request_queue *q)
 \tif (!e)
 \t\treturn;
 
-\tif ((q->nr_hw_queues == 1 ||
-\t\t\tblk_mq_is_shared_tags(q->tag_set->flags))) {
-\t\terr = elevator_change(q, &ctx);
-\t\tif (err < 0)
-\t\t\tpr_warn("\\\"%s\\\" elevator initialization, failed %d, falling back to \\\"none\\\"\\n",
-\t\t\t\t\tctx.name, err);
-\t}
+\terr = elevator_change(q, &ctx);
+\tif (err < 0)
+\t\tpr_warn("\\\"%s\\\" elevator initialization, failed %d, falling back to \\\"none\\\"\\n",
+\t\t\t\tctx.name, err);
 \televator_put(e);
 }
'''


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


def port_adios_616(data: bytes, project_revision: str = ADIOS_SOURCE_REVISION) -> bytes:
    if project_revision != ADIOS_SOURCE_REVISION:
        raise base.ResolveError(
            f"ADIOS porter requires a reviewed {project_revision} revision; "
            f"currently reviewed: {ADIOS_SOURCE_REVISION}"
        )
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
    elevator_end = text.find("\ndiff --git ", elevator_at + 1)
    if elevator_end < 0:
        raise base.ResolveError("ADIOS r2 port: following setlocalversion diff is missing")
    # Replace only the target-specific elevator integration. Keep subsequent
    # upstream sections, including scripts/setlocalversion, in the port.
    text = text[:elevator_at + 1] + ELEVATOR_PATCH_616 + text[elevator_end + 1:]
    if text.count("+\tdata->shallow_depth = ad->async_depth;\n") != 1:
        raise base.ResolveError("ADIOS r2 raw queue-depth fix changed upstream")

    old_depth = '''+static void adios_depth_updated(struct request_queue *q) {
+\tstruct adios_data *ad = q->elevator->elevator_data;
+
+\tad->async_depth = q->async_depth;
+\tblk_mq_set_min_shallow_depth(q, ad->async_depth);
+}
'''
    new_depth = '''+static void adios_depth_updated(struct blk_mq_hw_ctx *hctx) {
+\tstruct blk_mq_tags *tags = hctx->sched_tags;
+\tsbitmap_queue_min_shallow_depth(&tags->bitmap_tags, 1);
+}
'''
    text = replace_exact(text, old_depth, new_depth, "depth-updated API")
    text = replace_exact(
        text,
        "+\tq->async_depth = q->nr_requests;\n",
        "+\tad->async_depth = q->nr_requests;\n",
        "scheduler-local initial async depth",
    )
    # On 6.16 this setting belongs to the scheduler sysfs directory, like
    # mq-deadline's async_depth. Keep it writable and do not reset the user's
    # value when a hardware context or queue depth changes.
    sysfs_anchor = "+// Define sysfs attributes\n"
    async_sysfs = '''+/* Valve 6.16 equivalent of the newer queue/async_depth control. */
+static ssize_t adios_async_depth_show(struct elevator_queue *e, char *page) {
+\tstruct adios_data *ad = e->elevator_data;
+\treturn sysfs_emit(page, "%u\\n", READ_ONCE(ad->async_depth));
+}
+
+static ssize_t adios_async_depth_store(struct elevator_queue *e,
+\t\tconst char *page, size_t count) {
+\tstruct adios_data *ad = e->elevator_data;
+\tunsigned int depth;
+\tint ret = kstrtouint(page, 10, &depth);
+
+\tif (ret)
+\t\treturn ret;
+\tif (!depth)
+\t\treturn -EINVAL;
+\tWRITE_ONCE(ad->async_depth, depth);
+\treturn count;
+}
+
'''
    text = replace_exact(text, sysfs_anchor, async_sysfs + sysfs_anchor, "async-depth sysfs control")
    text = replace_exact(
        text,
        "+static struct elv_fs_entry adios_sched_attrs[] = {\n",
        "+static struct elv_fs_entry adios_sched_attrs[] = {\n+\tAD_ATTR_RW(async_depth),\n",
        "async-depth sysfs registration",
    )

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
    # Upstream appends a blank EOF line to block/Makefile; remove only that
    # whitespace so strict source diff checks retain their normal settings.
    text = replace_exact(
        text,
        '@@ -39,3 +40,10 @@',
        '@@ -39,3 +40,9 @@',
        "Makefile whitespace hunk count",
    )
    text = replace_exact(
        text,
        '+\tmake -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean\n+\n',
        '+\tmake -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean\n',
        "Makefile blank EOF line",
    )
    # LRU Marie precedes ADIOS and implements this identical upstream change.
    # Keep an exact already-present assertion, failing if it is not applied.
    text = replace_exact(
        text,
        '-\t\t\techo "+"\n+\t\t\t#echo "+"\n',
        '-\t\t\t#echo "+"\n+\t\t\t#echo "+"\n',
        "setlocalversion prerequisite shared with LRU Marie",
    )

    # Use the proven Valve 6.16 target context rather than synthesizing a
    # monolithic hunk from an isolated function. Smaller exact hunks remain
    # resilient to unrelated line movement while preserving the 3.3.0 logic.
    encoded = text.encode("utf-8")
    if b'ADIOS_VERSION "3.3.0"' not in encoded:
        raise base.ResolveError("ADIOS adaptive port lost the 3.3.0 version marker")
    for marker in (
        b"sbitmap_queue_min_shallow_depth",
        b"adios_init_hctx",
        b"AD_ATTR_RW(async_depth)",
        b"data->shallow_depth = ad->async_depth;",
        b"diff --git a/scripts/setlocalversion b/scripts/setlocalversion",
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
        upstream_data = item["content_bytes"]
        item["upstream_sha256"] = hashlib.sha256(upstream_data).hexdigest()
        item["upstream_size"] = len(upstream_data)
        item["content_bytes"] = port_adios_616(upstream_data, item["project_version"])
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
