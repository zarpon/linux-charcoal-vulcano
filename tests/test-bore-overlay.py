#!/usr/bin/env python3
import json
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base_path = root / "6.16.12-bore-6.8.0-rc1.patch"
overlay_paths = [
    root / "6.16.12-bore-6.8.0-final.patch",
    root / "6.16.12-bore-7.0.0.patch",
]
policy = json.loads((root / "automation/patch-source-overrides.json").read_text(encoding="utf-8"))
bore = policy["components"]["bore"]
assert bore["local_port_project_version"] == "7.0.0"
assert bore["local_port_upstream_sha256"] == "529ac503052e2ea09d9c54cbf536ffaac842ba436ff368c4a595585f46e7b709"
assert bore["local_port_overlays"] == [path.name for path in overlay_paths]

port70 = overlay_paths[-1].read_text(encoding="utf-8")
for marker in (
    '#define SCHED_BORE_VERSION  "7.0.0"',
    "sched_credit_cap_us = 16000",
    "DEFINE_STATIC_KEY_FALSE(sched_credit_key)",
    "bore_note_sleep(p, rq_clock(rq));",
    "u64 credit = bore_credit_ns(task_of(se));",
    "static_branch_likely(&sched_bore_key) &&",
):
    assert marker in port70, marker

assert "place_from" not in port70
assert 'SCHED_BORE_VERSION  "7.0.0-rc1"' not in port70

combined = base_path.read_bytes()
for overlay_path in overlay_paths:
    subprocess.run(["git", "apply", "--numstat", str(overlay_path)], cwd=root, check=True, text=True, capture_output=True)
    data = overlay_path.read_bytes()
    start = data.find(b"diff --git ")
    assert start >= 0
    if not combined.endswith(b"\n"):
        combined += b"\n"
    combined += data[start:]

with tempfile.NamedTemporaryFile(suffix=".patch") as merged:
    merged.write(combined)
    merged.flush()
    subprocess.run(["git", "apply", "--numstat", merged.name], cwd=root, check=True, text=True, capture_output=True)

if (root / "logs/patch-lock.json").is_file():
    subprocess.run(["python3", "automation/audit-latest-patch-versions.py"], cwd=root, check=True)

print("BORE 7.0.0 Valve 6.16.12 port policy, syntax and latest-patch audit passed")
