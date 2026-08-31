#!/usr/bin/env python3
import json
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
overlay_path = root / "6.16.12-bore-6.8.0-final.patch"
base_path = root / "6.16.12-bore-6.8.0-rc1.patch"
overlay = overlay_path.read_text(encoding="utf-8")
policy = json.loads((root / "automation/patch-source-overrides.json").read_text(encoding="utf-8"))
bore = policy["components"]["bore"]
assert bore["local_port_project_version"] == "6.8.0"
assert bore["local_port_upstream_sha256"] == "f650285feb58e9f3654836c8f84fb82723c30b3ad77a26cea5f218ce41ed7b14"
assert bore["local_port_overlays"] == ["6.16.12-bore-6.8.0-final.patch"]
for marker in (
    '#define SCHED_BORE_VERSION  "6.8.0"',
    "static inline u8 bore_score(struct task_struct *p)",
    "prio += bore_score(p);",
    "kernel/sched/build_utility.c",
    '__PS("bore.score", bore_score(p));',
):
    assert marker in overlay, marker
assert '+#define SCHED_BORE_VERSION  "6.8.0-rc1"' not in overlay

# Parse the overlay independently, then parse exactly the byte composition used
# by the resolver. --numstat validates unified-diff structure without requiring
# a checked-out kernel tree.
subprocess.run(
    ["git", "apply", "--numstat", str(overlay_path)],
    cwd=root,
    check=True,
    text=True,
    capture_output=True,
)
base = base_path.read_bytes()
overlay_bytes = overlay_path.read_bytes()
diff_start = overlay_bytes.find(b"diff --git ")
assert diff_start >= 0
if not base.endswith(b"\n"):
    base += b"\n"
with tempfile.NamedTemporaryFile(suffix=".patch") as combined:
    combined.write(base + overlay_bytes[diff_start:])
    combined.flush()
    subprocess.run(
        ["git", "apply", "--numstat", combined.name],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )

# The main workflow creates the lock immediately before this test. When present,
# enforce that every versioned patch family resolved the newest upstream release
# and that static local ports still correspond to the exact upstream bytes.
if (root / "logs/patch-lock.json").is_file():
    subprocess.run(
        ["python3", "automation/audit-latest-patch-versions.py"],
        cwd=root,
        check=True,
    )

print("BORE 6.8.0 Valve overlay policy, syntax and latest-patch audit passed")
