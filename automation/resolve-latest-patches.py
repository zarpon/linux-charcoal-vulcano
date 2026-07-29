#!/usr/bin/env python3
"""Resolve every applied remote patch from its current upstream source."""
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
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
UA = "linux-charcoal-vulcano-dynamic-resolver/5"


class ResolveError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    path: str
    sha: str
    url: str
    compatibility: int
    kernel_version: tuple[int, ...] | None
    project_version: str | None


_TREE_CACHE: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}


def request_json(url: str, token: str | None = None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        headers |= {
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=45
        ) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ResolveError(f"unable to read {url}: {exc}") from exc


def request_bytes(url: str, token: str | None = None) -> bytes:
    headers = {"User-Agent": UA}
    if token and url.startswith(API):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=90
        ) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise ResolveError(f"unable to download {url}: {exc}") from exc


def version_key(text: str | None) -> tuple[int, ...]:
    values = [int(value) for value in re.findall(r"\d+", text or "")]
    return tuple(values[-8:]) if values else (0,)


def parse_kernel_version(text: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    return (
        tuple(int(value) for value in match.groups() if value is not None)
        if match
        else None
    )


def regex_value(spec: dict[str, Any], key: str, path: str, group: str) -> str | None:
    expression = spec.get(key)
    if not expression:
        return None
    match = re.search(str(expression), path)
    if not match:
        return None
    return match.groupdict().get(group) or match.group(1)


def candidate_kernel_version(spec: dict[str, Any], path: str) -> tuple[int, ...] | None:
    raw = regex_value(spec, "kernel_version_regex", path, "kernel")
    return parse_kernel_version(raw) if raw else None


def candidate_project_version(spec: dict[str, Any], path: str) -> str | None:
    return regex_value(spec, "project_version_regex", path, "version")


def compatible_key(candidate: Candidate) -> tuple[Any, ...]:
    return (
        candidate.compatibility,
        version_key(candidate.project_version),
        candidate.kernel_version or (0,),
        candidate.path,
    )


def latest_key(candidate: Candidate) -> tuple[Any, ...]:
    return (
        version_key(candidate.project_version or candidate.path),
        candidate.kernel_version or (0,),
        candidate.path,
    )


def nearest_candidate(candidates: list[Candidate], kernel_version: str) -> Candidate | None:
    target = parse_kernel_version(kernel_version)
    if target is None:
        raise ResolveError(f"invalid kernel version: {kernel_version}")

    def distance(candidate: Candidate) -> int:
        version = candidate.kernel_version or ()
        left = version + (0,) * (3 - len(version))
        right = target + (0,) * (3 - len(target))
        return (
            abs(left[0] - right[0]) * 1_000_000
            + abs(left[1] - right[1]) * 1_000
            + abs(left[2] - right[2])
        )

    versioned = [item for item in candidates if item.kernel_version]
    if not versioned:
        return None
    minimum = min(distance(item) for item in versioned)
    return max((item for item in versioned if distance(item) == minimum), key=latest_key)


def paged(url: str, token: str | None) -> Iterable[Any]:
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        data = request_json(f"{url}{separator}per_page=100&page={page}", token)
        if not isinstance(data, list):
            raise ResolveError(f"expected a list from {url}")
        yield from data
        if len(data) < 100:
            return
        page += 1


def resolve_kernel_tag(config: dict[str, Any], token: str | None) -> tuple[str, str]:
    pattern = re.compile(config["tag_regex"])
    required = config.get("version")
    if required:
        prefix = urllib.parse.quote(str(required), safe="")
        tags: Iterable[Any] = request_json(
            f"{API}/repos/{config['repository']}/git/matching-refs/tags/{prefix}", token
        )
        if not isinstance(tags, list):
            raise ResolveError("expected a list from matching tag refs")
    else:
        tags = paged(f"{API}/repos/{config['repository']}/tags", token)

    matches: list[tuple[tuple[int, ...], str, str, str | None]] = []
    for item in tags:
        annotated_url = None
        if "ref" in item:
            name = str(item["ref"]).removeprefix("refs/tags/")
            obj = item.get("object", {})
            sha = obj.get("sha")
            annotated_url = obj.get("url") if obj.get("type") == "tag" else None
        else:
            name = item.get("name", "")
            sha = item.get("commit", {}).get("sha")
        match = pattern.fullmatch(name)
        if not match or "-rc" in name.lower():
            continue
        if required and match.group("version") != required:
            continue
        if sha:
            score = version_key(match.group("version")) + version_key(match.group("valve"))
            matches.append((score, name, sha, annotated_url))
    if not matches:
        raise ResolveError("no Valve SteamOS 6.16 tag matched")
    _, name, sha, annotated_url = max(matches)
    if annotated_url:
        sha = request_json(annotated_url, token).get("object", {}).get("sha", sha)
    return name, sha


def repository_tree(repo: str, branch: str, token: str | None) -> tuple[str, dict[str, Any]]:
    key = (repo, branch)
    if key not in _TREE_CACHE:
        encoded = urllib.parse.quote(branch, safe="")
        branch_data = request_json(f"{API}/repos/{repo}/branches/{encoded}", token)
        commit = branch_data["commit"]["sha"]
        tree = request_json(f"{API}/repos/{repo}/git/trees/{commit}?recursive=1", token)
        if tree.get("truncated"):
            raise ResolveError(
                f"GitHub tree for {repo}@{branch} was truncated; refusing a partial search"
            )
        _TREE_CACHE[key] = commit, tree
    return _TREE_CACHE[key]


def upstream_candidates(
    spec: dict[str, Any], kernel_version: str, token: str | None
) -> list[Candidate]:
    repo = spec["repository"]
    commit, tree = repository_tree(repo, spec.get("ref", "main"), token)
    include = re.compile(spec["filename_regex"])
    exclude = re.compile(spec["exclude_regex"]) if spec.get("exclude_regex") else None
    target = parse_kernel_version(kernel_version)
    if target is None:
        raise ResolveError(f"invalid kernel version: {kernel_version}")
    result: list[Candidate] = []
    for item in tree.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob" or not include.match(path):
            continue
        if exclude and exclude.search(path):
            continue
        kernel = candidate_kernel_version(spec, path)
        compatibility = (
            0
            if spec.get("always_latest")
            else 3
            if kernel == target
            else 2
            if kernel and kernel[:2] == target[:2]
            else 0
        )
        result.append(
            Candidate(
                path,
                commit,
                f"https://raw.githubusercontent.com/{repo}/{commit}/{path}",
                compatibility,
                kernel,
                candidate_project_version(spec, path),
            )
        )
    return result


def looks_like_patch(data: bytes) -> bool:
    return bool(data) and data.startswith(
        (b"From ", b"From:", b"diff --git", b"--- ", b"---\n")
    )


def decode_mailbox_patch(data: bytes) -> bytes:
    """Extract the patch payload from a MIME-encoded mailing-list message."""
    message = BytesParser(policy=policy.default).parsebytes(data)
    part = message.get_body(preferencelist=("plain",)) or message
    payload = part.get_payload(decode=True)
    if payload is None:
        content = part.get_content()
        if isinstance(content, bytes):
            payload = content
        elif isinstance(content, str):
            payload = content.encode(part.get_content_charset() or "utf-8")
        else:
            raise ResolveError("mailbox body is not text")

    payload = payload.replace(b"\r\n", b"\n")
    if payload.startswith(b"---\n"):
        patch = payload
    else:
        separator = payload.find(b"\n---\n")
        if separator < 0:
            raise ResolveError("mailbox body does not contain a patch separator")
        patch = payload[separator + 1 :]

    trailer = patch.find(b"\n-- \n")
    if trailer >= 0:
        patch = patch[:trailer]
    if not looks_like_patch(patch):
        raise ResolveError("decoded mailbox body is not a patch")
    return patch


def resolve_github_component(
    spec: dict[str, Any], kernel_version: str, token: str | None, root: Path
) -> dict[str, Any]:
    candidates = upstream_candidates(spec, kernel_version, token)
    if not candidates:
        raise ResolveError(f"no official upstream patch found for {spec['name']}")
    compatible = [item for item in candidates if item.compatibility >= 2]
    local_port = spec.get("local_port")
    adaptive_port = spec.get("adaptive_port")
    use_local_port = False
    use_adaptive_port = False
    if spec.get("always_latest"):
        candidate = max(candidates, key=latest_key)
        use_local_port = bool(local_port)
        use_adaptive_port = bool(adaptive_port)
        selection = (
            "latest-upstream-port"
            if use_local_port
            else "latest-upstream-adaptive-port"
            if use_adaptive_port
            else "latest-upstream"
        )
    elif spec.get("port_for_kernel") == kernel_version:
        candidate = (
            max(compatible, key=compatible_key)
            if compatible
            else nearest_candidate(candidates, kernel_version)
        )
        if (
            not candidate
            or not (local_port or adaptive_port)
            or not spec.get("port_when_incompatible", True)
        ):
            raise ResolveError(f"approved port is unavailable for {spec['name']}")
        use_local_port = bool(local_port)
        use_adaptive_port = bool(adaptive_port)
        selection = "upstream-port" if use_local_port else "upstream-adaptive-port"
    elif compatible:
        candidate = max(compatible, key=compatible_key)
        selection = "upstream-compatible"
    else:
        candidate = nearest_candidate(candidates, kernel_version)
        if candidate and spec.get("allow_nearest_upstream"):
            selection = "nearest-upstream"
        else:
            if (
                not candidate
                or not (local_port or adaptive_port)
                or not spec.get("port_when_incompatible")
            ):
                raise ResolveError(
                    f"no compatible upstream patch or approved port for {spec['name']}"
                )
            use_local_port = bool(local_port)
            use_adaptive_port = bool(adaptive_port)
            selection = (
                "nearest-upstream-port"
                if use_local_port
                else "nearest-upstream-adaptive-port"
            )

    upstream: dict[str, Any] = {
        "repository": spec["repository"],
        "path": candidate.path,
        "commit": candidate.sha,
        "url": candidate.url,
        "selection": selection,
    }
    if candidate.kernel_version:
        upstream["kernel_version"] = ".".join(map(str, candidate.kernel_version))
    if candidate.project_version:
        upstream["project_version"] = candidate.project_version
    if not use_local_port and not use_adaptive_port:
        return {**upstream, "origin": "upstream-compatible"}

    official = request_bytes(candidate.url, token)
    if not looks_like_patch(official):
        raise ResolveError(f"selected upstream source is not a patch: {candidate.url}")

    if use_adaptive_port:
        return {
            **upstream,
            "origin": "adaptive-port",
            "adapter": str(adaptive_port),
            "content_bytes": official,
        }

    path = root / str(local_port)
    base_data = path.read_bytes() if path.is_file() else b""
    if not base_data or not looks_like_patch(base_data):
        raise ResolveError(f"local port is missing or invalid: {local_port}")
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
        if not data.endswith(b"\n"):
            data += b"\n"
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


def resolve_http_component(
    spec: dict[str, Any], kernel_version: str, token: str | None, root: Path
) -> dict[str, Any]:
    series = ".".join(kernel_version.split(".")[:2])
    errors: list[str] = []
    for template in spec.get("urls", []):
        url = str(template).format(kernel_version=kernel_version, series=series)
        try:
            data = request_bytes(url, token)
            if spec.get("mailbox"):
                data = decode_mailbox_patch(data)
            if not looks_like_patch(data):
                raise ResolveError("response is not a patch")
            upstream = {
                "repository": spec.get("repository", url),
                "path": spec.get("path"),
                "commit": spec.get("commit"),
                "url": url,
                "selection": "first-valid",
            }
            local_port = spec.get("local_port")
            if not local_port:
                return {
                    **upstream,
                    "origin": "upstream-fixed",
                    "content_bytes": data,
                }

            path = root / str(local_port)
            local_data = path.read_bytes() if path.is_file() else b""
            if not local_data or not looks_like_patch(local_data):
                raise ResolveError(f"local port is missing or invalid: {local_port}")

            official_sha = hashlib.sha256(data).hexdigest()
            expected_sha = spec.get("local_port_upstream_sha256")
            if not expected_sha:
                raise ResolveError(
                    f"unversioned local port for {spec['name']} must declare "
                    "local_port_upstream_sha256"
                )
            if official_sha != expected_sha:
                raise ResolveError(
                    f"local port for {spec['name']} follows upstream SHA-256 "
                    f"{expected_sha}, but current upstream is {official_sha}; "
                    "refresh and validate the port"
                )

            upstream |= {"sha256": official_sha, "size": len(data)}
            return {
                "repository": "zarpon/linux-charcoal-vulcano",
                "path": str(local_port),
                "commit": "repository-local",
                "url": None,
                "origin": "local-port",
                "selection": "first-valid-port",
                "upstream": upstream,
                "local_port_overlays": [],
                "content_bytes": local_data,
            }
        except ResolveError as exc:
            errors.append(f"{url}: {exc}")
    raise ResolveError(f"no usable URL for {spec['name']}: {' | '.join(errors)}")


def resolve_component(
    spec: dict[str, Any], kernel_version: str, token: str | None, root: Path
) -> dict[str, Any]:
    kind = spec.get("kind", "github_tree")
    if kind == "github_tree":
        return resolve_github_component(spec, kernel_version, token, root)
    if kind == "http_patch":
        return resolve_http_component(spec, kernel_version, token, root)
    raise ResolveError(f"unknown component kind {kind!r} for {spec['name']}")


def replace_assignment(text: str, variable: str, value: str) -> str:
    updated, count = re.subn(
        rf"(?m)^{re.escape(variable)}=.*$", f"{variable}={value}", text, count=1
    )
    if count != 1:
        raise ResolveError(f"assignment {variable} not found in PKGBUILD")
    return updated


def find_array_bounds(text: str, variable: str) -> tuple[int, int]:
    start = re.search(rf"(?m)^{re.escape(variable)}=\(", text)
    if not start:
        raise ResolveError(f"{variable} array not found")
    end = re.search(r"(?m)^\s*\)\s*$", text[start.end() :])
    if not end:
        raise ResolveError(f"unterminated {variable} array")
    return start.start(), start.end() + end.end()


def normalized_source_line(line: str) -> str:
    value = line.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def replace_source_entries(
    text: str, components: list[dict[str, Any]], replacements: dict[str, str]
) -> str:
    start, end = find_array_bounds(text, "source")
    lines = text[start:end].splitlines(keepends=True)
    for spec in components:
        target = replacements[spec["name"]]
        if any(normalized_source_line(line) == target for line in lines):
            continue
        matches = [
            index
            for index, line in enumerate(lines)
            if re.fullmatch(str(spec["source_regex"]), normalized_source_line(line))
        ]
        if len(matches) != 1:
            raise ResolveError(
                f"source entry for {spec['name']}: expected one match, found {len(matches)}"
            )
        newline = "\n" if lines[matches[0]].endswith("\n") else ""
        lines[matches[0]] = f"  {target}{newline}"
    return text[:start] + "".join(lines) + text[end:]


def replace_sha_array_with_skip(text: str) -> str:
    source_start, source_end = find_array_bounds(text, "source")
    count = sum(
        1
        for line in text[source_start:source_end].splitlines()[1:-1]
        if line.strip() and not line.lstrip().startswith("#")
    )
    sha_start, sha_end = find_array_bounds(text, "sha256sums")
    array = "sha256sums=(\n" + "\n".join("  'SKIP'" for _ in range(count)) + "\n)"
    return text[:sha_start] + array + text[sha_end:]


def validate_manifest(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if manifest.get("schema") != 2:
        raise ResolveError("unsupported patch source manifest schema")
    groups = {
        "components": list(manifest.get("components", [])),
        "auxiliary_components": list(manifest.get("auxiliary_components", [])),
    }
    all_components = groups["components"] + groups["auxiliary_components"]
    names = [str(item.get("name", "")) for item in all_components]
    targets = [str(item.get("target", "")) for item in all_components]
    if not names or any(not name for name in names) or len(set(names)) != len(names):
        raise ResolveError("patch component names must be non-empty and unique")
    if any(not target for target in targets) or len(set(targets)) != len(targets):
        raise ResolveError("patch component targets must be non-empty and unique")
    if any(not item.get("source_regex") for item in all_components):
        raise ResolveError("every patch component requires source_regex")
    for item in all_components:
        local_port = item.get("local_port")
        adaptive_port = item.get("adaptive_port")
        kind = item.get("kind", "github_tree")
        if local_port and adaptive_port:
            raise ResolveError(
                f"{item['name']}: local_port and adaptive_port are mutually exclusive"
            )
        if item.get("mailbox") and kind != "http_patch":
            raise ResolveError(f"{item['name']}: mailbox decoding requires http_patch")
        if kind == "http_patch" and local_port and not item.get(
            "local_port_upstream_sha256"
        ):
            raise ResolveError(
                f"{item['name']}: local http port requires local_port_upstream_sha256"
            )
        if adaptive_port and (
            kind != "github_tree"
            or not isinstance(adaptive_port, str)
            or not adaptive_port
        ):
            raise ResolveError(
                f"{item['name']}: adaptive_port requires a non-empty github_tree adapter name"
            )
    return groups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="automation/patch-sources.json")
    parser.add_argument("--overrides", default="automation/patch-source-overrides.json")
    parser.add_argument("--pkgbuild", default="PKGBUILD")
    parser.add_argument("--lock", default="logs/patch-lock.json")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fixture")
    args = parser.parse_args()

    root = Path.cwd()
    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
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
    groups = validate_manifest(manifest)
    all_components = groups["components"] + groups["auxiliary_components"]
    pkgbuild_path = root / args.pkgbuild
    pkgbuild = pkgbuild_path.read_text(encoding="utf-8")
    token = os.environ.get("GITHUB_TOKEN")

    if args.fixture:
        fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        kernel_tag = fixture["kernel_tag"]
        kernel_sha = fixture.get("kernel_sha", "fixture")
        selected_groups = {
            name: fixture.get(name, {}) for name in ("components", "auxiliary_components")
        }
    else:
        kernel_tag, kernel_sha = resolve_kernel_tag(manifest["kernel_source"], token)
        kernel_version = kernel_tag.split("-valve", 1)[0]
        selected_groups = {
            name: {
                spec["name"]: resolve_component(spec, kernel_version, token, root)
                for spec in specs
            }
            for name, specs in groups.items()
        }

    kernel_version = kernel_tag.split("-valve", 1)[0]
    lock: dict[str, Any] = {
        "schema": 3,
        "kernel": {"tag": kernel_tag, "version": kernel_version, "commit": kernel_sha},
        "components": {},
        "auxiliary_components": {},
    }
    replacements: dict[str, str] = {}
    for group_name, specs in groups.items():
        selected = selected_groups[group_name]
        for spec in specs:
            name, target, item = spec["name"], spec["target"], selected[spec["name"]]
            if "content_bytes" in item:
                data = item["content_bytes"]
            elif args.fixture:
                data = item.get("content", "fixture patch\n").encode()
            elif item.get("origin") == "local-port":
                data = (root / item["path"]).read_bytes()
            else:
                data = request_bytes(item["url"], token)
            if not (looks_like_patch(data) or data.startswith(b"fixture")):
                raise ResolveError(f"patch for {name} does not look valid")
            clean = {
                key: value
                for key, value in item.items()
                if key not in {"content_bytes", "content"}
            }
            lock[group_name][name] = {
                **clean,
                "target": target,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
            replacements[name] = target
            if args.write:
                (root / target).write_bytes(data)

    updated = replace_assignment(pkgbuild, "_tag", kernel_tag)
    updated = replace_source_entries(updated, all_components, replacements)
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
