#!/usr/bin/env python3
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
assert '+#define SCHED_BORE_VERSION  "6.8.0-rc1"' not in overlay
print("BORE 6.8.0 Valve overlay policy passed")
