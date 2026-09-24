#!/usr/bin/env python3
"""Adapt a structurally verified POC patch to the Valve/BORE scheduler layout.

The resolver locks the exact upstream POC source bytes, commit, path and SHA-256.
This adapter preserves that selected POC revision's functionality while relocating
only reviewed scheduler hunks when the post-BORE Valve tree changes their context.
Unreviewed source shapes are rejected instead of falling back to an older patch.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

SECTION_HEADER = "diff --git a/kernel/sched/sched.h b/kernel/sched/sched.h\n"
FAIR_SECTION_HEADER = "diff --git a/kernel/sched/fair.c b/kernel/sched/fair.c\n"
LEGACY_ADDITIONS = "+#ifdef CONFIG_SCHED_POC_SELECTOR\n+\tunsigned int\t\tpoc_idle_committed;\n+#endif\n"
CURRENT_ADDITIONS = "+#ifdef CONFIG_SCHED_POC_SELECTOR\n+\tunsigned int\t\tpoc_idle_committed;\n+\tu64\t\t\tpoc_busy_bit;\t/* lazy commit: pre-shifted busy bit (0 = idle), lazy mode */\n+#endif\n"
FIELD_BLOCK = LEGACY_ADDITIONS
SCHED_ANCHOR_RE = re.compile(r"(?m)^(#ifdef CONFIG_SMP\n\tunsigned int\t\tttwu_pending;\n#endif\n\tu64\t\t\tnr_switches;\n)")
TTWU_CONTEXT_RE = re.compile(r"(?m)^[ \t]*unsigned int[ \t]+ttwu_pending;[ \t]*\n")
NATIVE_72_NOHZ_CONTEXT_RE = re.compile(r"(?m)^ [ \t]*call_single_data_t[ \t]+nohz_csd;[ \t]*\n^ #endif /\* CONFIG_NO_HZ_COMMON \*/[ \t]*\n")
NATIVE_72_UCLAMP_CONTEXT_RE = re.compile(r"(?m)^ #ifdef CONFIG_UCLAMP_TASK[ \t]*\n")
HUNK_RE = re.compile(r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<context>.*\n)$")
IDLE_SIBLING_DECLARATION = "static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu);\n"
IDLE_SIBLING_SYNC_DECLARATION = "static int select_idle_sibling(struct task_struct *p, int prev_cpu, int cpu, int sync);\n"
PELT_INCLUDE = ' #include "pelt.h"\n'
VALVE_SMP_GUARD = " #ifdef CONFIG_SMP\n"

class PortError(RuntimeError): pass

def sched_section(text):
    start=text.find(SECTION_HEADER)
    if start<0: raise PortError("POC patch does not contain kernel/sched/sched.h")
    end=text.find("\ndiff --git ",start+len(SECTION_HEADER))
    return text[start:len(text) if end<0 else end]

def section_bounds(text,header,description):
    start=text.find(header)
    if start<0: raise PortError(f"POC patch does not contain {description}")
    end=text.find("\ndiff --git ",start+len(header))
    return start,len(text) if end<0 else end

def next_hunk_end(text,hunk,section_end):
    n=text.find("\n@@ ",hunk+1,section_end)
    return section_end if n<0 else n+1

def increment_hunk_context(header):
    m=HUNK_RE.match(header)
    if not m: raise PortError("select_idle_sibling hunk header changed upstream")
    oc=int(m.group("old_count") or "1")+1; nc=int(m.group("new_count") or "1")+1
    return f"@@ -{m.group('old_start')},{oc} +{m.group('new_start')},{nc} @@{m.group('context')}"

def old_hunk_text(body):
    out=[]
    for line in body.splitlines(keepends=True):
        if line.startswith("+"): continue
        if line.startswith(("-"," ")): out.append(line[1:]); continue
        raise PortError("select_idle_sibling hunk has unsupported patch syntax")
    return "".join(out)

def rebase_hunk_header(header,body,source):
    m=HUNK_RE.match(header)
    if not m: raise PortError("select_idle_sibling hunk header changed upstream")
    old=old_hunk_text(body); off=source.find(old)
    if off<0: raise PortError("select_idle_sibling context does not match Valve/BORE fair.c")
    if source.find(old,off+1)>=0: raise PortError("select_idle_sibling context is ambiguous in Valve/BORE fair.c")
    line=source.count("\n",0,off)+1; old_start=int(m.group("old_start")); new_start=int(m.group("new_start"))
    return f"@@ -{line},{m.group('old_count') or '1'} +{line+new_start-old_start},{m.group('new_count') or '1'} @@{m.group('context')}"

def reviewed_idle_sibling_hunk(text):
    fs,fe=section_bounds(text,FAIR_SECTION_HEADER,"kernel/sched/fair.c"); candidate=None; h=text.find("@@ ",fs,fe)
    while h>=0:
        he=text.find("\n",h,fe)
        if he<0: raise PortError("select_idle_sibling hunk is malformed")
        he+=1; hend=next_hunk_end(text,h,fe); body=text[he:hend]
        if f"-{IDLE_SIBLING_DECLARATION}" in body and f"+{IDLE_SIBLING_SYNC_DECLARATION}" in body:
            if candidate is not None: raise PortError("multiple select_idle_sibling hunks found upstream")
            candidate=(h,he,hend,body)
        h=text.find("@@ ",hend,fe)
    if candidate is None: raise PortError("reviewed select_idle_sibling hunk was not found")
    return candidate

def adapt_idle_sibling_hunk(text,fair_source=None):
    h,he,hend,body=reviewed_idle_sibling_hunk(text)
    if body.count(PELT_INCLUDE)!=1: raise PortError("select_idle_sibling hunk no longer has one pelt.h anchor")
    if VALVE_SMP_GUARD in body: raise PortError("select_idle_sibling hunk already has a CONFIG_SMP guard")
    body2=body.replace(PELT_INCLUDE,PELT_INCLUDE+VALVE_SMP_GUARD)
    header=increment_hunk_context(text[h:he])
    if fair_source is not None: header=rebase_hunk_header(header,body2,fair_source)
    return text[:h]+header+body2+text[hend:]

def sched_hunk(sched_header,field_block=FIELD_BLOCK):
    if "poc_idle_committed" in sched_header: raise PortError("kernel/sched/sched.h already contains poc_idle_committed")
    matches=list(SCHED_ANCHOR_RE.finditer(sched_header))
    if len(matches)!=1: raise PortError(f"expected one Valve/BORE ttwu_pending anchor, found {len(matches)}")
    m=matches[0]; line=sched_header.count("\n",0,m.start())+1; lines=m.group(1).splitlines(keepends=True); added=field_block.count("\n")
    return f"@@ -{line},4 +{line},{4+added} @@ struct rq {{\n"+"".join(f" {x}" for x in lines[:2])+field_block+"".join(f" {x}" for x in lines[2:])

def insert_sched_hunk(text,header):
    s,e=section_bounds(text,SECTION_HEADER,"kernel/sched/sched.h"); first=text.find("@@ ",s,e)
    if first<0: raise PortError("POC patch has no remaining kernel/sched/sched.h hunk")
    return text[:first]+header+text[first:]

def is_native_72_sched_context(body): return bool(NATIVE_72_NOHZ_CONTEXT_RE.search(body) and NATIVE_72_UCLAMP_CONTEXT_RE.search(body))

def reviewed_sched_field_hunk(text,s,e):
    candidate=None; h=text.find("@@ ",s,e)
    while h>=0:
        he=text.find("\n",h,e)
        if he<0: raise PortError("rq::poc_idle_committed hunk is malformed")
        hend=next_hunk_end(text,h,e); body=text[he+1:hend]
        if LEGACY_ADDITIONS in body or CURRENT_ADDITIONS in body:
            if body.count("poc_idle_committed")!=1 or not (TTWU_CONTEXT_RE.search(body) or is_native_72_sched_context(body)): raise PortError("rq::poc_idle_committed hunk changed upstream")
            if candidate is not None: raise PortError("multiple rq::poc_idle_committed hunks found upstream")
            candidate=(h,hend,body)
        h=text.find("@@ ",hend,e)
    if candidate is None: raise PortError("reviewed rq::poc_idle_committed hunk was not found")
    return candidate

def adapt_patch(text,fair_source=None,sched_header=None):
    s,e=section_bounds(text,SECTION_HEADER,"kernel/sched/sched.h"); h,n,body=reviewed_sched_field_hunk(text,s,e)
    field=CURRENT_ADDITIONS if CURRENT_ADDITIONS in body else LEGACY_ADDITIONS
    adapted=text[:h]+text[n:]
    if "poc_idle_committed" in sched_section(adapted): raise PortError("rq::poc_idle_committed hunk remains in sched.h")
    # Both native 7.2 and legacy POC revisions are relocated against the actual
    # post-BORE Valve tree. This keeps the exact locked upstream revision while
    # avoiding stale native context after BORE changes sched.h/fair.c.
    if sched_header is not None: adapted=insert_sched_hunk(adapted,sched_hunk(sched_header,field))
    return adapt_idle_sibling_hunk(adapted,fair_source)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--validate",action="store_true"); p.add_argument("patch",type=Path); p.add_argument("output",type=Path,nargs="?"); p.add_argument("sched_header",type=Path,nargs="?"); p.add_argument("fair_source",type=Path,nargs="?"); a=p.parse_args()
    if a.validate:
        if a.output or a.sched_header or a.fair_source: p.error("--validate accepts only the upstream patch path")
        try: adapt_patch(a.patch.read_text(encoding="utf-8"))
        except (UnicodeDecodeError,PortError) as exc: raise SystemExit(f"POC Valve port failed: {exc}") from exc
        print("POC Valve adapter accepted the current upstream hunk; the exact source bytes are recorded in patch-lock.json"); return
    if not a.output or not a.sched_header or not a.fair_source: p.error("output, sched_header and fair_source are required unless --validate is used")
    try: out=adapt_patch(a.patch.read_text(encoding="utf-8"),a.fair_source.read_text(encoding="utf-8"),a.sched_header.read_text(encoding="utf-8"))
    except (UnicodeDecodeError,PortError) as exc: raise SystemExit(f"POC Valve port failed: {exc}") from exc
    a.output.write_text(out,encoding="utf-8"); print("Prepared the locked upstream POC patch by explicitly porting reviewed scheduler hunks to the post-BORE Valve layout")
if __name__=="__main__": main()
