#!/usr/bin/env python3
"""Resolve the newest official SteamOS linux-neptune-72 source package.

The official source index is authoritative for the package revision.  The
selected Arch package version is converted to the corresponding Valve
linux-integration tag and written into a generated patch manifest.  The exact
Arch/Valve base kernel config can optionally be extracted from the source
package, while the repository's config-neptune remains a separate fragment.
"""
from __future__ import annotations

import argparse
import dataclasses
import html.parser
import json
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import BinaryIO, Iterable

DEFAULT_INDEX = (
    "https://steamdeck-packages.steamos.cloud/archlinux-mirror/"
    "sources/jupiter-main/"
)
PACKAGE_RE = re.compile(
    r"^linux-neptune-72-(?P<pkgver>.+)-(?P<pkgrel>[0-9]+)\.src\.tar\.gz$"
)
USER_AGENT = "linux-charcoal-vulcano-steamos-7.2-resolver/1"


class PrepareError(RuntimeError):
    pass


class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


@dataclasses.dataclass(frozen=True)
class NeptunePackage:
    filename: str
    pkgver: str
    pkgrel: int
    url: str

    @property
    def tag(self) -> str:
        return package_version_to_tag(self.pkgver)

    @property
    def rank(self) -> tuple[int, ...]:
        return package_rank(self.pkgver, self.pkgrel)


def request(url: str, *, timeout: int = 90) -> BinaryIO:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as exc:
        raise PrepareError(f"unable to read {url}: {exc}") from exc


def fetch_text(url: str) -> str:
    with request(url, timeout=45) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def packages_from_html(html: str, index_url: str = DEFAULT_INDEX) -> list[NeptunePackage]:
    parser = LinkParser()
    parser.feed(html)
    packages: dict[str, NeptunePackage] = {}
    for href in parser.hrefs:
        filename = PurePosixPath(urllib.parse.urlparse(href).path).name
        match = PACKAGE_RE.fullmatch(filename)
        if not match:
            continue
        item = NeptunePackage(
            filename=filename,
            pkgver=match.group("pkgver"),
            pkgrel=int(match.group("pkgrel")),
            url=urllib.parse.urljoin(index_url, href),
        )
        packages[filename] = item
    return list(packages.values())


def package_rank(pkgver: str, pkgrel: int) -> tuple[int, ...]:
    """Return an order where a final 7.2 release outranks any 7.2 RC.

    SteamOS/Arch versions use dots where the git tag uses dashes, for example
    7.2.0.rc3.valve.beta1.  The rank also preserves Valve beta/serial and Arch
    package release ordering.
    """
    tokens = pkgver.split(".")
    numbers: list[int] = []
    pos = 0
    while pos < len(tokens) and len(numbers) < 3 and tokens[pos].isdigit():
        numbers.append(int(tokens[pos]))
        pos += 1
    while len(numbers) < 3:
        numbers.append(0)

    rc = -1
    valve_serial = 0
    valve_is_final = 1
    valve_beta = 0
    extra_numbers: list[int] = []
    for token in tokens[pos:]:
        if match := re.fullmatch(r"rc([0-9]+)", token):
            rc = int(match.group(1))
            continue
        if match := re.fullmatch(r"valve([0-9]+)", token):
            valve_serial = int(match.group(1))
            valve_is_final = 1
            continue
        if token == "valve":
            valve_is_final = 0
            continue
        if match := re.fullmatch(r"beta([0-9]+)", token):
            valve_beta = int(match.group(1))
            valve_is_final = 0
            continue
        extra_numbers.extend(int(value) for value in re.findall(r"[0-9]+", token))

    kernel_is_final = int(rc < 0)
    rc_order = rc if rc >= 0 else 1_000_000
    return (
        *numbers,
        kernel_is_final,
        rc_order,
        valve_is_final,
        valve_serial,
        valve_beta,
        *extra_numbers[-4:],
        pkgrel,
    )


def newest_package(packages: Iterable[NeptunePackage]) -> NeptunePackage:
    items = list(packages)
    if not items:
        raise PrepareError("official index contains no linux-neptune-72 source package")
    return max(items, key=lambda item: (item.rank, item.filename))


def package_version_to_tag(pkgver: str) -> str:
    tokens = pkgver.split(".")
    if len(tokens) < 3 or not all(token.isdigit() for token in tokens[:3]):
        raise PrepareError(f"unsupported linux-neptune-72 version: {pkgver}")
    tag = ".".join(tokens[:3])
    remainder = tokens[3:]
    for token in remainder:
        if re.fullmatch(r"rc[0-9]+", token):
            tag += f"-{token}"
        elif token == "valve":
            tag += "-valve"
        elif re.fullmatch(r"valve[0-9]+", token):
            tag += f"-{token}"
        elif re.fullmatch(r"(?:alpha|beta|rc)[0-9]+", token):
            tag += f"-{token}"
        elif token:
            tag += f"-{token}"
    if "-valve" not in tag:
        raise PrepareError(f"SteamOS package does not encode a Valve tag: {pkgver}")
    return tag


def extract_config_from_tar(fileobj: BinaryIO, destination: Path) -> str:
    """Extract the package's top-level Arch base config from a tar.gz stream."""
    candidates: list[tuple[int, tarfile.TarInfo, bytes]] = []
    try:
        with tarfile.open(fileobj=fileobj, mode="r|gz") as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                if not member.isfile() or path.name != "config":
                    continue
                if member.size < 50_000 or member.size > 5_000_000:
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                data = extracted.read()
                if b"CONFIG_64BIT=" not in data and b"CONFIG_X86_64=" not in data:
                    continue
                # Prefer the shallow package-level config over nested source files.
                candidates.append((len(path.parts), member, data))
                if len(path.parts) <= 2:
                    break
    except (tarfile.TarError, OSError) as exc:
        raise PrepareError(f"unable to extract Arch config: {exc}") from exc
    if not candidates:
        raise PrepareError("source package does not contain a usable x86_64 config")
    _, member, data = min(candidates, key=lambda item: item[0])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return member.name


def generated_manifest(base: dict[str, object], package: NeptunePackage) -> dict[str, object]:
    result = json.loads(json.dumps(base))
    result["kernel_source"] = {
        "repository": "evlaV/linux-integration",
        "series": "7.2",
        "preferred_tag": package.tag,
        "allow_prerelease": True,
        "tag_regex": (
            r"(?P<version>7\.2(?:\.[0-9]+)?(?:-rc[0-9]+)?)"
            r"-valve(?P<valve>.*)"
        ),
    }
    return result


def write_metadata(path: Path, package: NeptunePackage, config_member: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "package": dataclasses.asdict(package),
                "tag": package.tag,
                "config_member": config_member,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-url", default=DEFAULT_INDEX)
    parser.add_argument("--index-html", help="offline HTML fixture")
    parser.add_argument("--manifest-in", default="automation/patch-sources.json")
    parser.add_argument("--manifest-out", default="logs/patch-sources-7.2.json")
    parser.add_argument("--metadata", default="logs/steamos-7.2-source.json")
    parser.add_argument("--config-out", default="config")
    parser.add_argument("--fetch-config", action="store_true")
    parser.add_argument("--archive", help="offline source package fixture")
    args = parser.parse_args()

    if args.index_html:
        html = Path(args.index_html).read_text(encoding="utf-8")
    else:
        html = fetch_text(args.index_url)
    package = newest_package(packages_from_html(html, args.index_url))

    base = json.loads(Path(args.manifest_in).read_text(encoding="utf-8"))
    manifest_out = Path(args.manifest_out)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(
        json.dumps(generated_manifest(base, package), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    config_member: str | None = None
    if args.archive:
        with Path(args.archive).open("rb") as stream:
            config_member = extract_config_from_tar(stream, Path(args.config_out))
    elif args.fetch_config:
        with request(package.url, timeout=180) as stream:
            config_member = extract_config_from_tar(stream, Path(args.config_out))

    write_metadata(Path(args.metadata), package, config_member)
    print(f"package={package.filename}")
    print(f"tag={package.tag}")
    print(f"source={package.url}")
    if config_member:
        print(f"config={config_member}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PrepareError, OSError, json.JSONDecodeError) as exc:
        print(f"SteamOS 7.2 preparation error: {exc}", file=sys.stderr)
        raise SystemExit(2)
