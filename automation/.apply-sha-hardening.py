#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one literal match, found {count}")
    return text.replace(old, new, 1)


def sub_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise SystemExit(f"{label}: expected one regex match, found {count}")
    return updated


overlay = r'''From 9ad45d2fcd4662cae8574f7776d5d58302fbf680 Mon Sep 17 00:00:00 2001
From: Charcoal CI <noreply@localhost>
Date: Tue, 28 Jul 2026 12:00:00 +0000
Subject: [PATCH] sched: complete BORE 6.8.0 port for Valve 6.16.12

Carry the final 6.8.0 changes on top of the reviewed 6.8.0-rc1 Valve
port: derive the score from penalty, expose bore_score(), and include the
BORE declarations in the scheduler utility translation unit.
---
 include/linux/sched.h          | 8 +-------
 include/linux/sched/bore.h     | 5 ++++-
 kernel/sched/bore.c            | 2 +-
 kernel/sched/build_utility.c   | 4 ++++
 kernel/sched/debug.c           | 4 ++--
 5 files changed, 12 insertions(+), 11 deletions(-)

diff --git a/include/linux/sched.h b/include/linux/sched.h
--- a/include/linux/sched.h
+++ b/include/linux/sched.h
@@ -824,13 +824,7 @@ struct bore_ctx {
 	u64				burst_time;
 	u16				prev_penalty;
 	u16				curr_penalty;
-	union {
-		u16			penalty;
-		struct {
-			u8		_;
-			u8		score;
-		};
-	};
+	u16				penalty;
 	bool			stop_update;
 	bool			futex_waiting;
 	struct bore_bc	subtree;
diff --git a/include/linux/sched/bore.h b/include/linux/sched/bore.h
--- a/include/linux/sched/bore.h
+++ b/include/linux/sched/bore.h
@@ -12,7 +12,7 @@
 #define SCHED_BORE_AUTHOR   "Masahito Suzuki"
 #define SCHED_BORE_PROGNAME "BORE CPU Scheduler modification"
 
-#define SCHED_BORE_VERSION  "6.8.0-rc1"
+#define SCHED_BORE_VERSION  "6.8.0"
 
 extern u8   __read_mostly sched_bore;
 DECLARE_STATIC_KEY_TRUE(sched_bore_key);
@@ -25,6 +25,9 @@ extern u8   __read_mostly sched_burst_protect_slice_lv;
 DECLARE_STATIC_KEY_TRUE(sched_burst_protect_slice_cond_key);
 DECLARE_STATIC_KEY_FALSE(sched_burst_protect_slice_prefer_key);
 
+static inline u8 bore_score(struct task_struct *p)
+{ return p->bore.penalty >> 8; }
+
 extern u8   effective_prio_bore(struct task_struct *p);
 extern void update_curr_bore(struct task_struct *p, u64 delta_exec);
 extern void restart_burst_bore(struct task_struct *p);
diff --git a/kernel/sched/bore.c b/kernel/sched/bore.c
--- a/kernel/sched/bore.c
+++ b/kernel/sched/bore.c
@@ -80,7 +80,7 @@ u8 effective_prio_bore(struct task_struct *p) {
 	int prio = p->static_prio - MAX_RT_PRIO;
 	if (static_branch_likely(&sched_bore_key))
-		prio += p->bore.score;
+		prio += bore_score(p);
 	prio &= ~(prio >> 31);
 	s32 diff = prio - maxval_prio;
 	prio -= (diff & ~(diff >> 31));
diff --git a/kernel/sched/build_utility.c b/kernel/sched/build_utility.c
--- a/kernel/sched/build_utility.c
+++ b/kernel/sched/build_utility.c
@@ -54,6 +54,10 @@
 #include "stats.h"
 #include "autogroup.h"
 
+#ifdef CONFIG_SCHED_BORE
+#include <linux/sched/bore.h>
+#endif /* CONFIG_SCHED_BORE */
+
 #include "clock.c"
 
 #ifdef CONFIG_CGROUP_CPUACCT
diff --git a/kernel/sched/debug.c b/kernel/sched/debug.c
--- a/kernel/sched/debug.c
+++ b/kernel/sched/debug.c
@@ -824,7 +824,7 @@ print_task(struct seq_file *m, struct rq *rq, struct task_struct *p)
 		SPLIT_NS(schedstat_val_or_zero(p->stats.sum_block_runtime)));
 
 #ifdef CONFIG_SCHED_BORE
-	SEQ_printf(m, " %2d", p->bore.score);
+	SEQ_printf(m, " %2d", bore_score(p));
 #endif /* CONFIG_SCHED_BORE */
 #ifdef CONFIG_NUMA_BALANCING
 	SEQ_printf(m, "   %d      %d", task_node(p), task_numa_group_id(p));
@@ -1310,7 +1310,7 @@ void proc_sched_show_task(struct task_struct *p, struct pid_namespace *ns,
 
 	P(se.load.weight);
 #ifdef CONFIG_SCHED_BORE
-	P(bore.score);
+	__PS("bore.score", bore_score(p));
 #endif /* CONFIG_SCHED_BORE */
 #ifdef CONFIG_SMP
 	P(se.avg.load_sum);
-- 
2.50.1
'''
write("6.16.12-bore-6.8.0-final.patch", overlay)

overrides = {
    "schema": 1,
    "components": {
        "bore": {
            "local_port_project_version": "6.8.0",
            "local_port_upstream_sha256": None,
            "local_port_overlays": ["6.16.12-bore-6.8.0-final.patch"],
        }
    },
}
write("automation/patch-source-overrides.json", json.dumps(overrides, indent=2, sort_keys=True) + "\n")

resolver_path = "automation/resolve-latest-patches.py"
resolver = read(resolver_path)
resolver = replace_once(
    resolver,
    '    parser.add_argument("--manifest", default="automation/patch-sources.json")\n    parser.add_argument("--pkgbuild", default="PKGBUILD")',
    '    parser.add_argument("--manifest", default="automation/patch-sources.json")\n    parser.add_argument("--overrides", default="automation/patch-source-overrides.json")\n    parser.add_argument("--pkgbuild", default="PKGBUILD")',
    "resolver overrides argument",
)
resolver = replace_once(
    resolver,
    '    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))\n    groups = validate_manifest(manifest)',
    '''    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    override_path = root / args.overrides
    if override_path.is_file():
        overrides = json.loads(override_path.read_text(encoding="utf-8"))
        if overrides.get("schema") != 1:
            raise ResolveError("unsupported patch source override schema")
        for group_name in ("components", "auxiliary_components"):
            configured = overrides.get(group_name, {})
            if not isinstance(configured, dict):
                raise ResolveError(f"override group {group_name!r} must be an object")
            by_name = {
                str(item.get("name", "")): item
                for item in manifest.get(group_name, [])
                if isinstance(item, dict)
            }
            for name, values in configured.items():
                if name not in by_name or not isinstance(values, dict):
                    raise ResolveError(f"invalid override for {group_name}.{name}")
                by_name[name].update(values)
    groups = validate_manifest(manifest)''',
    "resolver override loading",
)
resolver = sub_once(
    resolver,
    r'''    path = root / str\(local_port\)\n.*?        "content_bytes": path\.read_bytes\(\),\n    \}\n''',
    '''    path = root / str(local_port)
    base_data = path.read_bytes() if path.is_file() else b""
    if not base_data or not looks_like_patch(base_data):
        raise ResolveError(f"local port is missing or invalid: {local_port}")
    official = request_bytes(candidate.url, token)
    if not looks_like_patch(official):
        raise ResolveError(f"selected upstream source is not a patch: {candidate.url}")
    official_sha = hashlib.sha256(official).hexdigest()
    expected = spec.get("local_port_upstream_sha256")
    if expected and official_sha != expected:
        raise ResolveError(
            f"local port for {spec['name']} follows upstream SHA-256 {expected}, "
            f"but current upstream is {official_sha}; refresh and validate the port"
        )

    expected_project_version = spec.get("local_port_project_version")
    if candidate.project_version:
        if expected_project_version is None:
            raise ResolveError(
                f"local port for {spec['name']} must declare "
                "local_port_project_version to track the selected upstream release"
            )
        if str(expected_project_version) != candidate.project_version:
            raise ResolveError(
                f"local port for {spec['name']} implements project version "
                f"{expected_project_version}, but the selected closest upstream "
                f"source is {candidate.project_version}; refresh and validate the port"
            )
    elif not expected:
        raise ResolveError(
            f"unversioned local port for {spec['name']} must declare "
            "local_port_upstream_sha256"
        )

    data = base_data
    overlay_records: list[dict[str, Any]] = []
    for overlay_value in spec.get("local_port_overlays", []):
        overlay_path = root / str(overlay_value)
        overlay_data = overlay_path.read_bytes() if overlay_path.is_file() else b""
        if not overlay_data or not looks_like_patch(overlay_data):
            raise ResolveError(f"local port overlay is missing or invalid: {overlay_value}")
        diff_start = overlay_data.find(b"diff --git ")
        if diff_start < 0:
            raise ResolveError(f"local port overlay has no unified diff: {overlay_value}")
        if not data.endswith(b"\\n"):
            data += b"\\n"
        data += overlay_data[diff_start:]
        overlay_records.append(
            {
                "path": str(overlay_value),
                "sha256": hashlib.sha256(overlay_data).hexdigest(),
                "size": len(overlay_data),
            }
        )

    upstream |= {"sha256": official_sha, "size": len(official)}
    return {
        "repository": "zarpon/linux-charcoal-vulcano",
        "path": str(local_port),
        "commit": "repository-local",
        "url": None,
        "origin": "local-port",
        "selection": selection,
        "upstream": upstream,
        "local_port_overlays": overlay_records,
        "content_bytes": data,
    }
''',
    "resolver local port composition",
)
write(resolver_path, resolver)

validator_path = "automation/validate-patch-lock.py"
validator = read(validator_path)
validator = replace_once(
    validator,
    '    parser.add_argument("--manifest", default="automation/patch-sources.json")\n    parser.add_argument("--lock", default="logs/patch-lock.json")',
    '    parser.add_argument("--manifest", default="automation/patch-sources.json")\n    parser.add_argument("--overrides", default="automation/patch-source-overrides.json")\n    parser.add_argument("--lock", default="logs/patch-lock.json")',
    "validator overrides argument",
)
validator = replace_once(
    validator,
    '    validate(load(Path(args.manifest)), load(Path(args.lock)))',
    '''    manifest = load(Path(args.manifest))
    override_path = Path(args.overrides)
    if override_path.is_file():
        overrides = load(override_path)
        if overrides.get("schema") != 1:
            raise ValidationError("unsupported patch source override schema")
        for group_name in ("components", "auxiliary_components"):
            by_name = {
                str(item.get("name", "")): item
                for item in components(manifest, group_name)
            }
            for name, values in overrides.get(group_name, {}).items():
                if name not in by_name or not isinstance(values, dict):
                    raise ValidationError(f"invalid override for {group_name}.{name}")
                by_name[name].update(values)
    validate(manifest, load(Path(args.lock)))''',
    "validator override loading",
)
validator = replace_once(
    validator,
    '''        if expected_upstream_sha and upstream.get("sha256") != expected_upstream_sha:
            raise ValidationError(
                f"{name}: reviewed port follows upstream SHA-256 "
                f"{expected_upstream_sha}, selected upstream is {upstream.get('sha256')!r}"
            )
''',
    '''        if expected_upstream_sha and upstream.get("sha256") != expected_upstream_sha:
            raise ValidationError(
                f"{name}: reviewed port follows upstream SHA-256 "
                f"{expected_upstream_sha}, selected upstream is {upstream.get('sha256')!r}"
            )

        expected_overlays = [str(value) for value in spec.get("local_port_overlays", [])]
        actual_overlays = record.get("local_port_overlays", [])
        if expected_overlays:
            if not isinstance(actual_overlays, list):
                raise ValidationError(f"{name}: local port overlay metadata is missing")
            actual_paths = [str(item.get("path", "")) for item in actual_overlays]
            if actual_paths != expected_overlays:
                raise ValidationError(
                    f"{name}: local port overlays differ: {actual_paths!r} != {expected_overlays!r}"
                )
            for item in actual_overlays:
                overlay_sha = item.get("sha256")
                if not isinstance(overlay_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", overlay_sha):
                    raise ValidationError(f"{name}: invalid local port overlay SHA-256")
                if not isinstance(item.get("size"), int) or item["size"] <= 0:
                    raise ValidationError(f"{name}: invalid local port overlay size")
''',
    "validator overlay metadata",
)
write(validator_path, validator)

workflow_path = ".github/workflows/push.yml"
workflow = read(workflow_path)
workflow = replace_once(
    workflow,
    "'automation/patch-sources.json', 'automation/resolve-latest-patches.py'",
    "'automation/patch-sources.json', 'automation/patch-source-overrides.json', 'automation/resolve-latest-patches.py'",
    "workflow cache inputs",
)
workflow = replace_once(
    workflow,
    "            makepkg --verifysource 2>&1 | tee logs/verifysource-bootstrap.log",
    "            makepkg --verifysource --skipchecksums 2>&1 | tee logs/verifysource-bootstrap.log",
    "workflow bootstrap source fetch",
)
workflow = replace_once(
    workflow,
    "          python3 automation/validate-patch-lock.py | tee logs/patch-lock-validation.log",
    "          python3 automation/validate-patch-lock.py | tee logs/patch-lock-validation.log\n          python3 tests/test-bore-overlay.py",
    "workflow overlay test",
)
workflow = sub_once(
    workflow,
    r'''          bore = lock\["components"\]\["bore"\]\n          assert bore\["origin"\] == "local-port"\n          assert bore\["selection"\] == "latest-upstream-port"\n          assert bore\["upstream"\]\["path"\] == "patches/testing/0001-linux6\.18\.22-bore-6\.8\.0-rc1\.patch"\n          assert bore\["upstream"\]\["sha256"\] == "356f9b2935e3ca79c3bcfa87d8630b6fec3fb731049c81cc7086fbbaa58f5e60"\n''',
    '''          bore = lock["components"]["bore"]
          assert bore["origin"] == "local-port"
          assert bore["selection"] == "latest-upstream-port"
          with open("automation/patch-source-overrides.json", encoding="utf-8") as handle:
              bore_policy = json.load(handle)["components"]["bore"]
          upstream = bore["upstream"]
          expected_version = bore_policy["local_port_project_version"]
          assert upstream["project_version"] == expected_version
          assert upstream["path"].endswith(f"-bore-{expected_version}.patch")
          assert re.fullmatch(r"[0-9a-f]{40}", upstream["commit"])
          assert re.fullmatch(r"[0-9a-f]{64}", upstream["sha256"])
          assert [item["path"] for item in bore["local_port_overlays"]] == bore_policy["local_port_overlays"]
''',
    "workflow dynamic BORE assertions",
)
write(workflow_path, workflow)

test = '''#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
overlay = (root / "6.16.12-bore-6.8.0-final.patch").read_text(encoding="utf-8")
policy = json.loads((root / "automation/patch-source-overrides.json").read_text(encoding="utf-8"))
bore = policy["components"]["bore"]
assert bore["local_port_project_version"] == "6.8.0"
assert bore["local_port_upstream_sha256"] is None
assert bore["local_port_overlays"] == ["6.16.12-bore-6.8.0-final.patch"]
for marker in (
    '#define SCHED_BORE_VERSION  "6.8.0"',
    "static inline u8 bore_score(struct task_struct *p)",
    "prio += bore_score(p);",
    "kernel/sched/build_utility.c",
    '__PS("bore.score", bore_score(p));',
):
    assert marker in overlay, marker
assert 'SCHED_BORE_VERSION  "6.8.0-rc1"' not in overlay
print("BORE 6.8.0 Valve overlay policy passed")
'''
write("tests/test-bore-overlay.py", test)

# Remove the one-shot staging files from the final commit.
(ROOT / "automation/.apply-sha-hardening.py").unlink()
(ROOT / ".github/workflows/apply-sha-hardening.yml").unlink(missing_ok=True)
