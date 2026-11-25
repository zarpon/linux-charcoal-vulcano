#!/usr/bin/env python3
"""Prepare current CAST bytes, trying the unmodified patch before any port.

Only reviewed context differences are adapted. Unknown API changes fail
git apply --check and require a reviewed port; no older release or partially
applied kernel tree is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path


def check(tree: Path, patch: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', '-C', str(tree), 'apply', '--check', str(patch.resolve())],
                          text=True, capture_output=True)


def adapt_reviewed_contexts(patch: str, tree: Path) -> tuple[str, list[str]]:
    sections = re.split(r'(?=^diff --git )', patch, flags=re.M)
    adaptations: list[str] = []

    folio_path = tree / 'mm/folio.c'
    folio = folio_path.read_text(encoding='utf-8') if folio_path.is_file() else ''
    folio_anchor = ' #include <linux/buffer_head.h>\n'
    folio_added = '+#include <linux/lru_cast.h>\n'
    folio_old = folio_anchor + folio_added
    folio_new = folio_anchor + ' #include <linux/kvm_types.h>\n' + folio_added

    sched_path = tree / 'kernel/sched/core.c'
    sched = sched_path.read_text(encoding='utf-8') if sched_path.is_file() else ''
    sched_old = (' \tpsi_account_irqtime(rq, curr, NULL);\n'
                 '+\t/* a task that runs on without switching still sets young bits */\n'
                 '+\tlru_cast_use_mm(rq->curr->mm);\n')
    sched_new = (' \tpsi_account_irqtime(rq, donor, NULL);\n'
                 '+\t/* a task that runs on without switching still sets young bits */\n'
                 '+\tlru_cast_use_mm(rq->curr->mm);\n')

    for index, section in enumerate(sections):
        if section.startswith('diff --git a/mm/folio.c b/mm/folio.c\n'):
            if '#include <linux/kvm_types.h>' in folio and section.count(folio_old) == 1:
                sections[index] = section.replace(folio_old, folio_new, 1)
                adaptations.append('folio-kvm-types-include')
            elif '#include <linux/kvm_types.h>' not in folio and section.count(folio_new) == 1:
                sections[index] = section.replace(folio_new, folio_old, 1)
                adaptations.append('folio-without-kvm-types-include')
        elif section.startswith('diff --git a/kernel/sched/core.c b/kernel/sched/core.c\n'):
            if 'psi_account_irqtime(rq, donor, NULL);' in sched and section.count(sched_old) == 1:
                sections[index] = section.replace(sched_old, sched_new, 1)
                adaptations.append('valve-sched-tick-donor-context')

    return ''.join(sections), adaptations




# Locked CAST v0.3.0 Valve 7.2.7 compatibility bridge, not a CAST downgrade.
# Source: official 7.3-rc7 v0.3.0 (SHA256 below), upstream ref
# c2aed944f2b7ca9fdf6ab549eccdf5b5f4f64812.
# Bridge: same official v0.3.0 6.18.62 variant (Git blob below).
# The 58 CAST core new-file additions are byte-identical in both official patches.
# Target: evlaV/linux-integration tag 7.2.7-valve2 commit 31504582a07316ae0e8a8fb3b8fdc39d94842816.
CAST_VALVE_SOURCE_SHA256 = "962359849dfbe6a7a67120cbeb2137d583e3d620b3e40f0bf4f4f161fc17010c"
CAST_VALVE_BRIDGE_BLOB = "45686da70242cbaa97dc29a52939ea0e0943790c"
CAST_VALVE_HEAD = "31504582a07316ae0e8a8fb3b8fdc39d94842816"
CAST_VALVE_BRIDGE = Path(__file__).resolve().parents[1] / "patches/ports/lru-cast-v0.3.0-6.18.62-upstream-bridge.patch"

CAST_VALVE_RMAP_HUNK = """@@ -904,6 +904,9 @@ static bool folio_referenced_one(struct folio *folio,
 \t\tif (lru_gen_enabled() && pvmw.pte) {
 \t\t\tif (lru_gen_look_around(&pvmw))
 \t\t\t\treferenced++;
+\t\t} else if (lru_cast_enabled() && pvmw.pte) {
+\t\t\tif (lru_cast_look_around(&pvmw))
+\t\t\t\treferenced++;
 \t\t} else if (pvmw.pte) {
 \t\t\tif (ptep_clear_flush_young_notify(vma, address,
 \t\t\t\t\t\tpvmw.pte))
"""
CAST_VALVE_RMAP_PORT = """@@ -980,6 +980,9 @@ static bool folio_referenced_one(struct folio *folio,
 \t\tif (lru_gen_enabled() && !lru_gen_switching() && pvmw.pte) {
 \t\t\tif (lru_gen_look_around(&pvmw, nr))
 \t\t\t\treferenced++;
+\t\t} else if (lru_cast_enabled() && pvmw.pte) {
+\t\t\tif (lru_cast_look_around(&pvmw))
+\t\t\t\treferenced++;
 \t\t} else if (pvmw.pte) {
 \t\t\tif (clear_flush_young_ptes_notify(vma, address, pvmw.pte, nr))
 \t\t\t\treferenced++;
"""


CAST_VALVE_VMSCAN_HUNK = "@@ -2037,10 +2160,18 @@ static unsigned long shrink_inactive_list(unsigned long nr_to_scan,\n \n \tlru_add_drain();\n \n+\t/* reclaim at work: the walker is to tell of what it is about to weigh */\n+\tif (lru_cast_on(lruvec))\n+\t\tlru_cast_walk_ask();\n+\n \tspin_lock_irq(&lruvec->lru_lock);\n \n-\tnr_taken = isolate_lru_folios(nr_to_scan, lruvec, &folio_list,\n-\t\t\t\t     &nr_scanned, sc, lru);\n"
CAST_VALVE_VMSCAN_PORT = "@@ -2037,10 +2160,18 @@ static unsigned long shrink_inactive_list(unsigned long nr_to_scan,\n \n \tlru_add_drain();\n \n+\t/* reclaim at work: the walker is to tell of what it is about to weigh */\n+\tif (lru_cast_on(lruvec))\n+\t\tlru_cast_walk_ask();\n+\n \tlruvec_lock_irq(lruvec);\n \n-\tnr_taken = isolate_lru_folios(nr_to_scan, lruvec, &folio_list,\n-\t\t\t\t     &nr_scanned, sc, lru);\n"
CAST_VALVE_VMSCAN_PREIMAGE = "\tlru_add_drain();\n\n\tlruvec_lock_irq(lruvec);\n\n\tnr_taken = isolate_lru_folios(nr_to_scan, lruvec, &folio_list,\n\t\t\t\t     &nr_scanned, sc, lru);"


def git_blob_digest(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def cast_core_additions(text: str) -> dict[str, str]:
    result = {}
    for section in re.split(r"(?=^diff --git a/)", text, flags=re.M):
        match = re.match(r"diff --git a/(.+?) b/", section)
        if not match:
            continue
        name = match.group(1)
        if name == "include/linux/lru_cast.h" or name.startswith("mm/lru_cast/"):
            result[name] = "\n".join(
                line[1:] for line in section.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            )
    return result




def adapt_valve_vmscan_lock_context(patch: str, tree: Path) -> str:
    """Port CAST reclaim to Valve's lruvec_lock_irq wrapper; keep CAST isolation intact."""
    sections = re.split(r"(?=^diff --git )", patch, flags=re.M)
    hits = 0
    for i, section in enumerate(sections):
        if not section.startswith("diff --git a/mm/vmscan.c b/mm/vmscan.c\n"):
            continue
        hits += 1
        if section.count(CAST_VALVE_VMSCAN_HUNK) != 1:
            raise RuntimeError("CAST Valve vmscan source hunk changed; review required")
        vmscan = (tree / "mm/vmscan.c").read_text(encoding="utf-8")
        if vmscan.count(CAST_VALVE_VMSCAN_PREIMAGE) != 1:
            raise RuntimeError("CAST Valve vmscan lock/API preimage changed; review required")
        sections[i] = section.replace(CAST_VALVE_VMSCAN_HUNK, CAST_VALVE_VMSCAN_PORT, 1)
    if hits != 1:
        raise RuntimeError("CAST Valve vmscan diff section missing/duplicated")
    return "".join(sections)

def reviewed_valve_cast_bridge(source: bytes, tree: Path, output: Path) -> str:
    if hashlib.sha256(source).hexdigest() != CAST_VALVE_SOURCE_SHA256:
        raise RuntimeError("unreviewed CAST upstream source SHA; refuse Valve bridge")
    actual_head = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if actual_head != CAST_VALVE_HEAD:
        raise RuntimeError("Valve kernel tree commit changed; re-review required")
    bridge_data = CAST_VALVE_BRIDGE.read_bytes()
    if git_blob_digest(bridge_data) != CAST_VALVE_BRIDGE_BLOB:
        raise RuntimeError("authenticated CAST 0.3.0 bridge blob changed")
    bridge = bridge_data.decode("utf-8")
    official_core = cast_core_additions(source.decode("utf-8"))
    bridge_core = cast_core_additions(bridge)
    if len(official_core) != 58 or official_core != bridge_core:
        raise RuntimeError("CAST 0.3.0 bridge changed functional core additions")
    if bridge.count(CAST_VALVE_RMAP_HUNK) != 1:
        raise RuntimeError("official bridge rmap hunk changed")
    rmap_target = "\n".join(
        line[1:] for line in CAST_VALVE_RMAP_PORT.splitlines()[1:]
        if line.startswith(" ")
    )
    if (tree / "mm/rmap.c").read_text(encoding="utf-8").count(rmap_target) != 1:
        raise RuntimeError("Valve rmap MGLRU switching and notifier context changed")
    bridge = bridge.replace(CAST_VALVE_RMAP_HUNK, CAST_VALVE_RMAP_PORT, 1)
    bridge = adapt_valve_vmscan_lock_context(bridge, tree)
    bridge, notes = adapt_reviewed_contexts(bridge, tree)
    if "valve-sched-tick-donor-context" not in notes:
        raise RuntimeError("Valve scheduler donor-context bridge not proven")
    output.write_text(bridge, encoding="utf-8", newline="\n")
    dry = subprocess.run(
        ["patch", "--dry-run", "--batch", "--forward", "--no-backup-if-mismatch",
         "--fuzz=3", "-p1", "-i", str(output.resolve())],
        cwd=tree, capture_output=True, text=True,
    )
    transcript = dry.stdout + dry.stderr
    if dry.returncode or "FAILED" in transcript or "saving rejects" in transcript:
        output.unlink(missing_ok=True)
        raise RuntimeError("CAST Valve 7.2 port still has incompatible hunks: " + transcript[-5000:])
    return "reviewed-valve-7.2.7-cast-0.3.0-fuzz"



def prepare(source: Path, output: Path, tree: Path) -> str:
    data = source.read_bytes()
    output.write_bytes(data)
    direct = check(tree, output)
    if direct.returncode == 0:
        return 'upstream-unmodified'

    adapted, adaptations = adapt_reviewed_contexts(data.decode('utf-8'), tree)
    if adaptations:
        output.write_text(adapted, encoding='utf-8', newline='\n')
        result = subprocess.run(['git', '-C', str(tree), 'apply', '--recount', '--check', str(output.resolve())],
                                text=True, capture_output=True)
        if result.returncode == 0:
            return 'ported-' + '+'.join(adaptations)
        detail = result.stderr
    else:
        detail = direct.stderr
    if (tree / ".git").exists() and (tree / "Makefile").is_file():
        try:
            return reviewed_valve_cast_bridge(data, tree, output)
        except (RuntimeError, OSError, subprocess.CalledProcessError):
            output.unlink(missing_ok=True)
            raise
    output.unlink()
    raise RuntimeError('latest CAST requires a reviewed kernel API port; refusing older release: ' + detail)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('tree', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('output must differ from locked upstream source')
    result = prepare(args.source, args.output, args.tree)
    for path in (args.source, args.output):
        print(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}')
    print(f'CAST preparation: {result}')


if __name__ == '__main__':
    main()
