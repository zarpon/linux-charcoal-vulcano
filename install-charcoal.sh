#!/usr/bin/env bash
# Install the newest verified Charcoal 6.18 SteamOS pre-release from the 618pre channel.

set -Eeuo pipefail

readonly REPOSITORY="zarpon/linux-charcoal-vulcano"
readonly RELEASES_API="https://api.github.com/repos/${REPOSITORY}/releases?per_page=100"
readonly RELEASE_DOWNLOAD_PREFIX="https://github.com/${REPOSITORY}/releases/download/"
readonly KERNEL_SERIES="6.18"
readonly PACKAGE_PREFIX="linux-charcoal-618"
readonly USER_AGENT="charcoal-kernel-installer"

WORKDIR=""
MADE_ROOT_WRITABLE=0

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '%s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

run_privileged() {
  if (( EUID == 0 )); then
    command "$@"
  else
    sudo "$@"
  fi
}

_update_grub() {
  local steamos_efi_dir=${1:-/efi/EFI/steamos}

  if command -v grub-mkconfig >/dev/null 2>&1; then
    if [[ -d "$steamos_efi_dir" ]]; then
      run_privileged grub-mkconfig -o "$steamos_efi_dir/grub.cfg"
    else
      run_privileged grub-mkconfig -o /boot/grub/grub.cfg
    fi
  elif command -v steamos-update-grub >/dev/null 2>&1; then
    run_privileged steamos-update-grub
  elif command -v update-grub >/dev/null 2>&1; then
    run_privileged update-grub
  else
    die "No supported bootloader update command found; update the bootloader manually before rebooting"
  fi
}

cleanup() {
  local exit_status=$?
  trap - EXIT

  if (( MADE_ROOT_WRITABLE )); then
    info "Restoring SteamOS read-only mode..."
    if ! run_privileged steamos-readonly enable; then
      printf 'warning: could not restore SteamOS read-only mode; run sudo steamos-readonly enable manually.\n' >&2
      exit_status=1
    fi
  fi

  if [[ -n "$WORKDIR" && -d "$WORKDIR" ]]; then
    rm -rf -- "$WORKDIR"
  fi

  exit "$exit_status"
}

download_file() {
  local url=$1
  local destination=$2

  curl \
    --fail \
    --silent \
    --show-error \
    --location \
    --proto '=https' \
    --proto-redir '=https' \
    --retry 3 \
    --connect-timeout 15 \
    --output "$destination" \
    "$url"
}

parse_release_metadata() {
  local release_json=$1

  python3 - "$release_json" "$REPOSITORY" "$RELEASE_DOWNLOAD_PREFIX" "$KERNEL_SERIES" <<'PY'
from datetime import datetime
import json
import re
import sys
from pathlib import PurePosixPath

release_json, repository, download_prefix, kernel_series = sys.argv[1:]
tag_pattern = re.compile(
    rf"^charcoal-{re.escape(kernel_series)}\.[0-9A-Za-z][0-9A-Za-z._-]*-pre-r[1-9][0-9]*$"
)

try:
    with open(release_json, encoding="utf-8") as handle:
        releases = json.load(handle)
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Could not parse the GitHub release response: {exc}")

if not isinstance(releases, list):
    raise SystemExit("GitHub did not return a release list")

def text(value, label):
    if not isinstance(value, str) or not value or any(char in value for char in "\x00\r\n"):
        raise SystemExit(f"Invalid {label} in the GitHub release response")
    return value

def asset_url(asset, expected_name, tag_name):
    name = text(asset.get("name"), "asset name")
    url = text(asset.get("browser_download_url"), "asset URL")
    if name != expected_name:
        raise SystemExit(f"Unexpected asset name: {name}")
    expected_prefix = f"{download_prefix}{tag_name}/"
    if not url.startswith(expected_prefix):
        raise SystemExit(f"Refusing asset outside release {tag_name} in {repository}: {url}")
    return name, url

def published_time(release):
    value = text(release.get("published_at"), "release publication time")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"Invalid release publication time: {value}") from exc

eligible = []
for release in releases:
    if not isinstance(release, dict) or release.get("draft") or not release.get("prerelease"):
        continue
    tag_name = text(release.get("tag_name"), "release tag")
    if not tag_pattern.fullmatch(tag_name):
        continue
    assets = release.get("assets")
    if not isinstance(assets, list):
        continue
    expected_archive_name = f"linux-{tag_name}.zip"
    archives = [
        asset for asset in assets
        if isinstance(asset, dict) and asset.get("name") == expected_archive_name
    ]
    checksums = [
        asset for asset in assets
        if isinstance(asset, dict) and asset.get("name") == "RELEASE-ZIP-SHA256SUM"
    ]
    if len(archives) == 1 and len(checksums) == 1:
        eligible.append(
            (published_time(release), tag_name, expected_archive_name, archives[0], checksums[0])
        )

if not eligible:
    raise SystemExit(
        f"GitHub did not return a published Charcoal {kernel_series} 618pre pre-release with verified assets"
    )

_, tag_name, expected_archive_name, archive, checksum = max(
    eligible, key=lambda item: (item[0], item[1])
)

archive_name, archive_url = asset_url(archive, expected_archive_name, tag_name)
checksum_name, checksum_url = asset_url(checksum, "RELEASE-ZIP-SHA256SUM", tag_name)

if PurePosixPath(archive_name).name != archive_name:
    raise SystemExit("Invalid release ZIP filename")

print(tag_name)
print(archive_name)
print(archive_url)
print(checksum_name)
print(checksum_url)
PY
}

verify_release_archive() {
  local archive=$1
  local checksum_file=$2
  local archive_name=$3

  python3 - "$archive" "$checksum_file" "$archive_name" <<'PY'
import hashlib
import re
import sys

archive, checksum_file, archive_name = sys.argv[1:]

try:
    lines = open(checksum_file, encoding="utf-8").read().splitlines()
except OSError as exc:
    raise SystemExit(f"Could not read release checksum: {exc}")

entries = []
for line in lines:
    match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
    if not match:
        raise SystemExit("Invalid RELEASE-ZIP-SHA256SUM format")
    entries.append((match.group(1).lower(), match.group(2)))

if len(entries) != 1 or entries[0][1] != archive_name:
    raise SystemExit("Release checksum does not match the selected ZIP")

digest = hashlib.sha256()
with open(archive, "rb") as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)

if digest.hexdigest() != entries[0][0]:
    raise SystemExit("Release ZIP SHA-256 verification failed")
PY
}

extract_and_verify_packages() {
  local archive=$1
  local destination=$2
  local package_prefix=$3

  python3 - "$archive" "$destination" "$package_prefix" <<'PY'
import hashlib
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

archive = Path(sys.argv[1])
destination = Path(sys.argv[2])
package_prefix = sys.argv[3]
package_pattern = re.compile(rf"^{re.escape(package_prefix)}-[^/\\\x00\r\n]+\.pkg\.tar\.zst$")
checksum_pattern = re.compile(rf"([0-9a-fA-F]{{64}}) [ *]({re.escape(package_prefix)}-[^/\\\x00\r\n]+\.pkg\.tar\.zst)")

try:
    with zipfile.ZipFile(archive) as handle:
        infos = handle.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("release ZIP contains duplicate entries")

        if "SHA256SUMS" not in names:
            raise ValueError("release ZIP is missing SHA256SUMS")

        package_infos = [info for info in infos if package_pattern.fullmatch(info.filename)]
        package_names = {info.filename for info in package_infos}
        if not package_infos:
            raise ValueError("release ZIP contains no Charcoal packages")
        if not any("-headers-" not in name for name in package_names):
            raise ValueError("release ZIP is missing the kernel package")
        if not any("-headers-" in name for name in package_names):
            raise ValueError("release ZIP is missing the headers package")

        for info in [next(info for info in infos if info.filename == "SHA256SUMS"), *package_infos]:
            if PurePosixPath(info.filename).name != info.filename:
                raise ValueError(f"unsafe path in release ZIP: {info.filename}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"symbolic link in release ZIP: {info.filename}")

        manifest = handle.read("SHA256SUMS").decode("utf-8")
        checksums = {}
        for line in manifest.splitlines():
            match = checksum_pattern.fullmatch(line)
            if not match:
                raise ValueError("invalid package SHA256SUMS format")
            digest, name = match.groups()
            if name in checksums:
                raise ValueError(f"duplicate checksum entry: {name}")
            checksums[name] = digest.lower()

        if set(checksums) != package_names:
            raise ValueError("package list does not exactly match SHA256SUMS")

        destination.mkdir(mode=0o700)
        checksum_target = destination / "SHA256SUMS"
        checksum_target.write_text(manifest, encoding="utf-8")

        for info in package_infos:
            package_target = destination / info.filename
            digest = hashlib.sha256()
            with handle.open(info) as source, package_target.open("xb") as target:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
                    target.write(block)
            if digest.hexdigest() != checksums[info.filename]:
                package_target.unlink(missing_ok=True)
                raise ValueError(f"package SHA-256 verification failed: {info.filename}")
except (OSError, ValueError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
    raise SystemExit(f"Could not verify release packages: {exc}")
PY
}

main() {
  require_command curl
  require_command python3
  require_command mktemp
  require_command pacman
  require_command steamos-readonly
  require_command steamos-devmode
  if (( EUID != 0 )); then
    require_command sudo
  fi

  WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/charcoal-installer.XXXXXX")"
  trap cleanup EXIT

  info "Fetching the latest published Charcoal ${KERNEL_SERIES} 618pre pre-release..."
  curl \
    --fail \
    --silent \
    --show-error \
    --location \
    --proto '=https' \
    --proto-redir '=https' \
    --retry 3 \
    --connect-timeout 15 \
    --header 'Accept: application/vnd.github+json' \
    --header 'X-GitHub-Api-Version: 2022-11-28' \
    --user-agent "$USER_AGENT" \
    --output "$WORKDIR/release.json" \
    "$RELEASES_API"

  local metadata
  if ! metadata="$(parse_release_metadata "$WORKDIR/release.json")"; then
    die "Could not identify the required assets in the latest Charcoal ${KERNEL_SERIES} 618pre pre-release"
  fi

  local -a fields
  mapfile -t fields <<< "$metadata"
  (( ${#fields[@]} == 5 )) || die "Incomplete GitHub release metadata"
  # GitHub/SteamOS uses LF, but strip a transport CR defensively so the
  # verified URLs cannot be altered by a CRLF-producing Python runtime.
  local index
  for index in "${!fields[@]}"; do
    fields[$index]=${fields[$index]%$'\r'}
  done

  local release_tag=${fields[0]}
  local archive_name=${fields[1]}
  local archive_url=${fields[2]}
  local checksum_name=${fields[3]}
  local checksum_url=${fields[4]}
  local archive_path="$WORKDIR/$archive_name"
  local checksum_path="$WORKDIR/$checksum_name"
  local package_dir="$WORKDIR/packages"

  info "Selected latest published 618pre kernel pre-release: ${release_tag}"
  info "Downloading release ${release_tag}..."
  download_file "$archive_url" "$archive_path"
  download_file "$checksum_url" "$checksum_path"

  info "Verifying release archive SHA-256..."
  verify_release_archive "$archive_path" "$checksum_path" "$archive_name"

  info "Extracting and verifying kernel package SHA-256 checksums..."
  extract_and_verify_packages "$archive_path" "$package_dir" "$PACKAGE_PREFIX"

  local -a packages
  mapfile -d '' -t packages < <(find "$package_dir" -maxdepth 1 -type f -name "${PACKAGE_PREFIX}-*.pkg.tar.zst" -print0 | sort -z)
  (( ${#packages[@]} >= 2 )) || die "Verified release does not contain the expected kernel and headers packages"

  info "Making SteamOS writable for the package transaction..."
  run_privileged steamos-readonly disable
  MADE_ROOT_WRITABLE=1

  info "Enabling SteamOS developer mode..."
  run_privileged steamos-devmode enable --no-prompt

  info "Installing ${release_tag}. Confirm the replacement of linux-neptune when pacman asks."
  # Releases carry a monotonically increasing GitHub revision while the
  # package version tracks Valve's base kernel. Do not use --needed here: it
  # would skip a verified newer release whose package version is unchanged.
  run_privileged pacman -U "${packages[@]}"

  info "Updating the bootloader configuration..."
  _update_grub

  info "Charcoal ${release_tag} was installed successfully. Reboot, then verify with: uname -r"
  info "ZRAM switches to LZ4 with ZSTD --fast=1 priority-1 recompression after booting Charcoal; the active swap is not reset during installation."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
