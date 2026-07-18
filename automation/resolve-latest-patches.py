#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
UA = "linux-charcoal-TD-dynamic-resolver/1"


class ResolveError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    path: str
    sha: str
    url: str
    score: tuple[int, ...]


def request_json(url: str, token: str | None = None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ResolveError(f"unable to read {url}: {exc}") from exc


def request_bytes(url: str, token: str | None = None) -> bytes:
    headers = {"User-Agent": UA}
    if token and url.startswith(API):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise ResolveError(f"unable to download {url}: {exc}") from exc


def version_key(text: str) -> tuple[int, ...]:
    numbers = [int(value) for value in re.findall(r"\d+", text)]
    return tuple(numbers[-6:]) if numbers else (0,)


def paged(url: str, token: str | None) -> Iterable[Any]:
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        data = request_json(f"{url}{sep}per_page=100&page={page}", token)
        if not isinstance(data, list):
            raise ResolveError(f"expected a list from {url}")
        yield from data
        if len(data) < 100:
            return
        page += 1


def resolve_kernel_tag(config: dict[str, Any], token: str | None) -> tuple[str, str]:
    repo = config["repository"]
    pattern = re.compile(config["tag_regex"])
    matches: list[tuple[tuple[int, ...], str, str]] = []
    for tag in paged(f"{API}/repos/{repo}/tags", token):
        name = tag.get("name", "")
        match = pattern.match(name)
        if not match:
            continue
        score = version_key(match.group("version")) + version_key(match.group("valve"))
        matches.append((score, name, tag["commit"]["sha"]))
    if not matches:
        raise ResolveError(f"no Valve kernel tag matched in {repo}")
    _, name, sha = max(matches)
    return name, sha


def get_default_branch(repo: str, token: str | None) -> str:
    branch = request_json(f"{API}/repos/{repo}", token).get("default_branch")
    if not branch:
        raise ResolveError(f"default branch unavailable for {repo}")
    return str(branch)


def resolve_component(component: dict[str, Any], kernel_version: str, token: str | None) -> Candidate:
    repo = component["repository"]
    branch = component.get("ref") or get_default_branch(repo, token)
    branch_data = request_json(f"{API}/repos/{repo}/branches/{urllib.parse.quote(branch, safe='')}", token)
    commit_sha = branch_data["commit"]["sha"]
    tree = request_json(f"{API}/repos/{repo}/git/trees/{commit_sha}?recursive=1", token)
    include = re.compile(component["filename_regex"])
    exclude = re.compile(component["exclude_regex"]) if component.get("exclude_regex") else None
    series = ".".join(kernel_version.split(".")[:2])
    full = kernel_version
    candidates: list[Candidate] = []
    for item in tree.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob" or not include.match(path):
            continue
        if exclude and exclude.search(path):
            continue
        compatibility = 3 if full in path else 2 if series in path else 1 if "latest" in path.lower() else 0
        if compatibility == 0:
            continue
        raw = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{path}"
        candidates.append(Candidate(path, commit_sha, raw, (compatibility,) + version_key(path)))
    if not candidates:
        raise ResolveError(f"no compatible patch found for {component['name']} ({kernel_version}) in {repo}")
    return max(candidates, key=lambda item: item.score)


def replace_assignment(text: str, variable: str, value: str) -> str:
    updated, count = re.subn(rf"(?m)^{re.escape(variable)}=.*$", f"{variable}={value}", text, count=1)
    if count != 1:
        raise ResolveError(f"assignment {variable} not found in PKGBUILD")
    return updated


def replace_source_entries(text: str, replacements: dict[str, str]) -> str:
    start = text.find("source=(")
    end = text.find("\n)", start)
    if start < 0 or end < 0:
        raise ResolveError("source array not found in PKGBUILD")
    block = text[start:end]
    patterns = {
        "lru_marie": r"(?m)^\s*6\.\d+(?:\.\d+)?-lru_marie-[^\s]+\.patch\s*$",
        "zram_ir": r"(?m)^\s*0001-linux[^\s]*-zram-ir-[^\s]+\.patch\s*$",
        "adios": r"(?m)^\s*6\.\d+(?:\.\d+)?-ADIOS-[^\s]+\.patch\s*$",
        "bore": r"(?m)^\s*6\.\d+(?:\.\d+)?-bore-[^\s]+\.patch\s*$",
        "poc_selector": r"(?m)^\s*6\.\d+(?:\.\d+)?-poc-selector-[^\s]+\.patch\s*$",
        "nap": r"(?m)^\s*6\.\d+(?:\.\d+)?-nap-v?[^\s]+\.patch\s*$"
    }
    for name, target in replacements.items():
        block, count = re.subn(patterns[name], f"  {target}", block, count=1)
        if count == 0 and target not in block:
            block += f"\n  {target}"
    return text[:start] + block + text[end:]


def replace_sha_array_with_skip(text: str) -> str:
    source_start = text.find("source=(")
    source_end = text.find("\n)", source_start)
    source_block = text[source_start:source_end]
    count = sum(1 for line in source_block.splitlines()[1:] if line.strip() and not line.strip().startswith("#"))
    sha_start = text.find("sha256sums=(")
    sha_end = text.find("\n)", sha_start)
    if sha_start < 0 or sha_end < 0:
        raise ResolveError("sha256sums array not found")
    array = "sha256sums=(\n" + "\n".join("  'SKIP'" for _ in range(count)) + "\n)"
    return text[:sha_start] + array + text[sha_end + 2:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="automation/patch-sources.json")
    parser.add_argument("--pkgbuild", default="PKGBUILD")
    parser.add_argument("--lock", default="logs/patch-lock.json")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fixture")
    args = parser.parse_args()

    root = Path.cwd()
    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    token = os.environ.get("GITHUB_TOKEN")
    pkgbuild_path = root / args.pkgbuild
    pkgbuild = pkgbuild_path.read_text(encoding="utf-8")

    if args.fixture:
        fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        kernel_tag = fixture["kernel_tag"]
        kernel_sha = fixture.get("kernel_sha", "fixture")
        selected = fixture["components"]
    else:
        kernel_tag, kernel_sha = resolve_kernel_tag(manifest["kernel_source"], token)
        kernel_version = kernel_tag.split("-valve", 1)[0]
        selected = {}
        for component in manifest["components"]:
            candidate = resolve_component(component, kernel_version, token)
            selected[component["name"]] = {
                "repository": component["repository"], "path": candidate.path,
                "commit": candidate.sha, "url": candidate.url
            }

    kernel_version = kernel_tag.split("-valve", 1)[0]
    lock: dict[str, Any] = {"schema": 1, "kernel": {"tag": kernel_tag, "version": kernel_version, "commit": kernel_sha}, "components": {}}
    replacements: dict[str, str] = {}
    for component in manifest["components"]:
        name = component["name"]
        item = selected[name]
        target = component["target"]
        data = item.get("content", "fixture patch\n").encode() if args.fixture else request_bytes(item["url"], token)
        if not data.startswith((b"From ", b"diff --git", b"--- ", b"fixture")):
            raise ResolveError(f"download for {name} does not look like a patch: {item['url']}")
        digest = hashlib.sha256(data).hexdigest()
        lock["components"][name] = {**item, "target": target, "sha256": digest, "size": len(data)}
        replacements[name] = target
        if args.write:
            destination = root / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

    updated = replace_assignment(pkgbuild, "_tag", kernel_tag)
    updated = replace_source_entries(updated, replacements)
    updated = replace_sha_array_with_skip(updated)
    if args.write:
        pkgbuild_path.write_text(updated, encoding="utf-8")

    lock_path = root / args.lock
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(lock, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ResolveError as exc:
        print(f"resolver error: {exc}", file=sys.stderr)
        raise SystemExit(2)
