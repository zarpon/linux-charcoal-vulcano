#!/usr/bin/env python3
"""Refresh bundled controller drivers once per build and pin immutable commits.

Use GitHub's latest published, non-prerelease release. xpad-noone currently
has no releases, so only that repository may use its default-branch HEAD.
Local builds: python3 automation/resolve-controller-drivers.py --write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORIES = {
    "xpadneo": "atar-axis/xpadneo",
    "xone": "dlundqvist/xone",
    "xpad-noone": "forkymcforkface/xpad-noone",
}


class ResolutionError(RuntimeError):
    pass


def github_json(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "linux-charcoal-controller-resolver",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request("https://api.github.com/" + path, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)
    raise ResolutionError("GitHub request retries exhausted")


def resolve_driver(name: str, request=github_json) -> dict:
    repository = REPOSITORIES[name]
    base = f"repos/{repository}"
    try:
        release = request(f"{base}/releases/latest")
    except urllib.error.HTTPError as exc:
        if name != "xpad-noone" or exc.code != 404:
            raise
        # Confirm an absent stable release, rather than masking an API failure.
        releases = request(f"{base}/releases?per_page=100")
        if not isinstance(releases, list) or any(
            not item.get("draft") and not item.get("prerelease") for item in releases
        ):
            raise ResolutionError(f"{repository}: inconsistent latest-release response")
        repo = request(base)
        ref = repo["default_branch"]
        mode = "default-branch-head-no-stable-release"
        release = None
    else:
        if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not False:
            raise ResolutionError(f"{repository}: latest release is not a published stable release")
        ref = release.get("tag_name", "")
        mode = "latest-release"
    if not isinstance(ref, str) or not ref or any(c.isspace() for c in ref):
        raise ResolutionError(f"{repository}: invalid release tag/default branch")
    commit = request(f"{base}/commits/{urllib.parse.quote(ref, safe='')}")
    sha = commit.get("sha", "")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ResolutionError(f"{repository}: invalid commit SHA")
    record = {"repository": repository, "mode": mode, "ref": ref, "commit": sha}
    if release is not None:
        record["release_url"] = release["html_url"]
        record["published_at"] = release["published_at"]
    return record


def update_pkgbuild(text: str, drivers: dict) -> str:
    version = drivers["xpadneo"]["ref"].removeprefix("v")
    if not re.fullmatch(r"[0-9][0-9A-Za-z.+_-]*", version):
        raise ResolutionError("invalid xpadneo VERSION value")
    text, count = re.subn(r"(?m)^_xpadneo_version=.*$", f"_xpadneo_version={version}", text)
    if count != 1:
        raise ResolutionError("expected exactly one _xpadneo_version assignment")
    for name, record in drivers.items():
        repository = record["repository"]
        pattern = rf'(?m)^\s*"git\+https://github\.com/{re.escape(repository)}\.git#[^"\n]+"\s*$'
        replacement = f'  "git+https://github.com/{repository}.git#commit={record["commit"]}"'
        text, count = re.subn(pattern, lambda _: replacement, text)
        if count != 1:
            raise ResolutionError(f"expected exactly one source for {name}")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pkgbuild", type=Path, default=Path("PKGBUILD"))
    parser.add_argument("--lock", type=Path, default=Path("logs/controller-driver-lock.json"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    # Resolve and validate all drivers before changing any build input.
    drivers = {name: resolve_driver(name) for name in REPOSITORIES}
    updated = update_pkgbuild(args.pkgbuild.read_text(encoding="utf-8"), drivers)
    if args.write:
        args.lock.parent.mkdir(parents=True, exist_ok=True)
        args.lock.write_text(json.dumps({"schema": 1, "drivers": drivers}, indent=2) + "\n", encoding="utf-8")
        args.pkgbuild.write_text(updated, encoding="utf-8")
    for name, record in drivers.items():
        print(f'{name}: {record["ref"]} -> {record["commit"]} ({record["mode"]})')
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ResolutionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Controller driver resolution failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
