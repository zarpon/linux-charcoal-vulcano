#!/usr/bin/env python3
"""Render auditable Charcoal release notes from the resolved build lock."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
PATCH_LABELS = {
    "adios": "ADIOS", "bore": "BORE", "bore_sched_ext_coexistence": "BORE sched_ext coexistence",
    "lru_cast": "LRU CAST", "nap": "NAP", "poc_selector": "POC Selector",
    "zram_ir": "ZRAM-IR", "cpu_optimizations": "CPU optimizations",
    "zen_interactive": "Zen Interactive", "reflex": "REFLEX",
}


def safe(value: object) -> str:
    """Keep untrusted lock metadata from producing markdown structure."""
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").replace("`", "'").strip()


def get_lock(path: Path) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(lock, dict) or not isinstance(lock.get("kernel"), dict):
        raise ValueError("patch lock has no kernel metadata")
    if not isinstance(lock.get("components"), dict) or not lock["components"]:
        raise ValueError("patch lock has no applied components")
    return lock


def format_components(components: dict) -> list[str]:
    lines = ["| Componente | Versão do patch | Série upstream | Seleção / origem |", "|---|---|---|---|"]
    details: list[str] = []
    for name, info in sorted(components.items()):
        if not isinstance(info, dict) or not SHA256_RE.fullmatch(str(info.get("sha256", ""))):
            raise ValueError(f"invalid patch SHA256 metadata: {name}")
        label = PATCH_LABELS.get(name, name.replace("_", " "))
        version = info.get("project_version") or "não registrada (consultar arquivo)"
        kernel_variant = info.get("kernel_version") or info.get("kernel_target") or "genérica / não declarada"
        selection = info.get("selection") or info.get("origin") or "não declarada"
        lines.append(f"| **{safe(label)}** | `{safe(version)}` | `{safe(kernel_variant)}` | {safe(selection)} |")
        path = info.get("selected_path") or info.get("path") or info.get("url") or "sem caminho"
        details.extend([
            f"**{safe(label)}** — fonte `{safe(path)}`",
            f"- SHA256 selecionado: `{info['sha256']}`",
        ])
        for key, heading in (("commit", "Commit upstream"), ("latest_upstream_project_version", "Revisão global mais recente")):
            if info.get(key):
                details.append(f"- {heading}: `{safe(info[key])}`")
        if isinstance(info.get("compatibility_reference"), dict):
            ref = info["compatibility_reference"]
            details.append(f"- Referência para porte: `{safe(ref.get('kernel_version', '?'))}` / `{safe(ref.get('project_version', '?'))}`")
        if isinstance(info.get("upstream"), dict):
            ref = info["upstream"]
            details.append(f"- Referência de porte local: `{safe(ref.get('repository', '?'))}/{safe(ref.get('path', '?'))}` @ `{safe(ref.get('commit', '?'))}`")
        if info.get("upstream_sha256"):
            details.append(f"- SHA256 original antes do porte: `{safe(info['upstream_sha256'])}`")
        details.append("")
    return lines + ["", "<details>", "<summary>Proveniência e SHA256 completos de cada patch</summary>", ""] + details + ["</details>"]


def render(mode: str, lock: dict, package_version: str, kernel_tag: str, zip_name: str, release_tag: str, sha: str, run_id: str) -> str:
    if mode not in {"stable", "preview"}:
        raise ValueError("unsupported release mode")
    kernel = lock["kernel"]
    series = '.'.join(str(kernel.get('version', '')).split('.')[:2])
    if not re.fullmatch(r'\d+\.\d+', series) or tuple(map(int, series.split('.'))) < (7, 2):
        raise ValueError(f"unsupported stable kernel series: {series}")
    if not str(kernel.get("version", "")).startswith(series + "."):
        raise ValueError(f"wrong kernel series for {mode} release: {kernel}")
    if kernel.get("tag") != kernel_tag:
        raise ValueError("kernel tag disagrees with the validated patch lock")
    if mode == "preview" and not release_tag.startswith("charcoal-7.2-preview-"):
        raise ValueError("preview tag has invalid prefix")
    if mode == "stable" and not release_tag.startswith(f"charcoal-{kernel['version']}."):
        raise ValueError("stable tag has invalid prefix")
    lines = [
        f"# Charcoal — SteamOS {'Preview' if mode == 'preview' else 'Stable'} / Linux {series} — {safe(package_version)}",
        "",
        "## Kernel e publicação",
        f"- **Kernel Valve (fonte):** `{safe(kernel_tag)}` — Linux `{safe(kernel['version'])}`.",
        f"- **Versão do pacote:** `{safe(package_version)}`; **tag desta publicação:** `{safe(release_tag)}`.",
        f"- **Linha:** `{'kernel-7.2' if mode == 'preview' else 'master'}`; **commit do build:** `{safe(sha)}`; **workflow run:** `{safe(run_id)}`.",
        "- **Tipo:** `draft=false`, `prerelease=true`, **não Latest**." if mode == "preview" else "- **Tipo:** `draft=false`, `prerelease=false`, **Latest estável**.",
        "",
        "## Patches aplicados e versões selecionadas",
        "Versões e origens abaixo são lidas do `patch-lock.json` validado **nesta execução**, não de valores fixos no workflow.",
        "",
        *format_components(lock["components"]),
    ]
    for group, heading in (("auxiliary_components", "Componentes auxiliares"),):
        if lock.get(group):
            lines.extend(["", f"## {heading}", "", *format_components(lock[group])])
    lines.extend([
        "", "## Artefatos e auditoria", f"- ZIP: `{safe(zip_name)}`.",
        "- Consulte o `patch-lock.json` da execução e os arquivos SHA256 dos artefatos para verificar os bytes realmente utilizados.",
        "- Os drivers e módulos adicionais são validados nos logs do build; não atribuímos versão a um driver ausente no lock de patches.",
    ])
    if mode == "preview":
        lines.append("- Preview é prerelease isolada, descoberta pelo instalador somente por `charcoal-7.2-preview-*`; não altera a release Latest estável.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("mode", "lock", "pkgver", "kernel-tag", "release-tag", "release-zip", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    lock = get_lock(Path(args.lock))
    text = render(args.mode, lock, args.pkgver, args.kernel_tag, args.release_zip,
                  args.release_tag, os.getenv("GITHUB_SHA", "local"), os.getenv("GITHUB_RUN_ID", "local"))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(text, encoding="utf-8")
    print(f"Generated {args.output}: {len(lock['components'])} patches from validated lock")


if __name__ == "__main__":
    main()
