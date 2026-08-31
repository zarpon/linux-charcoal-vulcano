#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
policy = json.loads((root / "automation/patch-sources.json").read_text(encoding="utf-8"))
components = {item["name"]: item for item in policy["components"]}
bore = components["bore"]
coexistence = components["bore_sched_ext_coexistence"]

assert bore["port_for_kernel"] == "6.18"
assert bore["local_port"] == "6.18.45-bore-6.8.0.port.patch"
assert bore["local_port_project_version"] == "6.8.0"
assert bore["local_port_upstream_sha256"] == (
    "4ac714dfd1f08f8a3eb60f33755789828192c7f28594217036ba890b00a01bcd"
)
assert "local_port_overlays" not in bore
assert coexistence["port_for_kernel"] == "6.18"
assert coexistence["local_port"] == "6.18.45-bore-sched-ext-coexistence-fix.port.patch"

ports = [
    root / str(bore["local_port"]),
    root / str(coexistence["local_port"]),
]
for port in ports:
    text = port.read_text(encoding="utf-8")
    assert "diff --git " in text, port
    subprocess.run(
        ["git", "apply", "--numstat", str(port)],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )

bore_text = ports[0].read_text(encoding="utf-8")
for marker in (
    '#define SCHED_BORE_VERSION  "6.8.0"',
    "static inline u8 bore_score(struct task_struct *p)",
    "prio += bore_score(p);",
    "kernel/sched/build_utility.c",
    '__PS("bore.score", bore_score(p));',
):
    assert marker in bore_text, marker
assert '+#define SCHED_BORE_VERSION  "6.8.0-rc1"' not in bore_text

coexistence_text = ports[1].read_text(encoding="utf-8")
assert "void reweight_task(struct task_struct *p, int prio)" in coexistence_text
assert "CONFIG_SCHED_BORE" in coexistence_text

# The main workflow creates the lock immediately before this test. When present,
# enforce that every versioned patch family resolved the newest upstream release
# and that reviewed ports still correspond to their exact upstream bytes.
if (root / "logs/patch-lock.json").is_file():
    subprocess.run(
        ["python3", "automation/audit-latest-patch-versions.py"],
        cwd=root,
        check=True,
    )

print("BORE 6.18-series ports, syntax and latest-patch audit passed")
