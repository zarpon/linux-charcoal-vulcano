#!/usr/bin/env bash
# Install the newest Charcoal SteamOS 7.2 prerelease from the kernel-7.2 line.

set -Eeuo pipefail

readonly REPOSITORY="zarpon/linux-charcoal-vulcano"
readonly RELEASES_API="https://api.github.com/repos/${REPOSITORY}/releases?per_page=100"
readonly RELEASE_DOWNLOAD_PREFIX="https://github.com/${REPOSITORY}/releases/download/"
readonly RELEASE_TAG_PREFIX="charcoal-7.2-"
readonly RELEASE_ZIP_PREFIX="linux-charcoal-72-"
readonly USER_AGENT="charcoal-kernel-7.2-installer"

WORKDIR=""
MADE_ROOT_WRITABLE=0
ROLLBACK_READY=0

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
  local releases_json=$1

  python3 - "$releases_json" "$REPOSITORY" "$RELEASE_DOWNLOAD_PREFIX" "$RELEASE_TAG_PREFIX" "$RELEASE_ZIP_PREFIX" <<'PY'
import json
import sys
from pathlib import PurePosixPath

releases_json, repository, download_prefix, tag_prefix, zip_prefix = sys.argv[1:]

try:
    with open(releases_json, encoding="utf-8") as handle:
        releases = json.load(handle)
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Could not parse the GitHub releases response: {exc}")

if not isinstance(releases, list):
    raise SystemExit("GitHub did not return a releases list")


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
        raise SystemExit(f"Refusing asset outside {repository} release {tag_name}: {url}")
    return name, url

selected = None
for release in releases:
    if not isinstance(release, dict):
        continue
    tag_name = release.get("tag_name")
    if (
        release.get("draft")
        or not release.get("prerelease")
        or not isinstance(tag_name, str)
        or not tag_name.startswith(tag_prefix)
    ):
        continue
    selected = release
    break

if selected is None:
    raise SystemExit("No published Charcoal SteamOS 7.2 prerelease was found")

tag_name = text(selected.get("tag_name"), "release tag")
assets = selected.get("assets")
if not isinstance(assets, list):
    raise SystemExit("GitHub prerelease has no assets")

archives = [
    asset for asset in assets
    if isinstance(asset, dict)
    and str(asset.get("name", "")).startswith(zip_prefix)
    and str(asset.get("name", "")).endswith(".zip")
]
checksums = [
    asset for asset in assets
    if isinstance(asset, dict) and asset.get("name") == "RELEASE-ZIP-SHA256SUM"
]

if len(archives) != 1:
    raise SystemExit("Expected exactly one SteamOS 7.2 Charcoal release ZIP")
if len(checksums) != 1:
    raise SystemExit("Expected exactly one RELEASE-ZIP-SHA256SUM asset")

archive_name = text(archives[0].get("name"), "archive name")
archive_name, archive_url = asset_url(archives[0], archive_name, tag_name)
checksum_name, checksum_url = asset_url(checksums[0], "RELEASE-ZIP-SHA256SUM", tag_name)

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

  python3 - "$archive" "$destination" <<'PY'
import hashlib
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

archive, destination = map(Path, sys.argv[1:])
package_pattern = re.compile(r"^linux-charcoal-72(?:-headers)?-[^/\\\x00\r\n]+\.pkg\.tar\.zst$")
checksum_pattern = re.compile(r"([0-9a-fA-F]{64}) [ *](linux-charcoal-72(?:-headers)?-[^/\\\x00\r\n]+\.pkg\.tar\.zst)")

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
        if len(package_infos) != 2:
            raise ValueError("release ZIP must contain exactly the SteamOS 7.2 kernel and headers packages")
        if sum("-headers-" in name for name in package_names) != 1:
            raise ValueError("release ZIP must contain exactly one headers package")
        if sum("-headers-" not in name for name in package_names) != 1:
            raise ValueError("release ZIP must contain exactly one kernel package")

        manifest_info = next(info for info in infos if info.filename == "SHA256SUMS")
        for info in [manifest_info, *package_infos]:
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

list_installed_charcoal_packages() {
  local installed_file=$1
  pacman -Qq > "$installed_file" || die "Could not query installed packages"
  local name
  while IFS= read -r name; do
    if [[ "$name" == linux-charcoal || "$name" == linux-charcoal-* ]]; then
      printf '%s\n' "$name"
    fi
  done < "$installed_file"
}

capture_rollback_packages() {
  local -n package_names=$1
  (( ${#package_names[@]} > 0 )) || return 0

  local rollback_dir="$WORKDIR/rollback"
  mkdir -p "$rollback_dir"
  local name version candidate found
  for name in "${package_names[@]}"; do
    version="$(pacman -Q "$name" 2>/dev/null | awk '{print $2}')" || true
    [[ -n "$version" ]] || { rm -rf "$rollback_dir"; return 0; }
    found=""
    for candidate in /var/cache/pacman/pkg/"${name}-${version}"-*.pkg.tar.zst; do
      if [[ -f "$candidate" ]]; then
        found=$candidate
        break
      fi
    done
    [[ -n "$found" ]] || { rm -rf "$rollback_dir"; return 0; }
    cp -- "$found" "$rollback_dir/"
  done
  ROLLBACK_READY=1
}

confirm_transaction() {
  local release_tag=$1
  shift
  local -a previous=("$@")

  info "Verified prerelease: ${release_tag}"
  if (( ${#previous[@]} )); then
    info "The following previous Charcoal packages will be removed before SteamOS 7.2 is installed:"
    printf '  - %s\n' "${previous[@]}"
  else
    info "No previous Charcoal kernel package is installed."
  fi
  info "The new packages are already downloaded and SHA-256 verified. The installer never reboots automatically."

  if [[ "${CHARCOAL_72_ASSUME_YES:-0}" == "1" ]]; then
    return 0
  fi
  [[ -t 0 ]] || die "Interactive confirmation is required; rerun in a terminal"

  local answer
  read -r -p "Continue with the SteamOS 7.2 prerelease installation? [s/N] " answer
  case "$answer" in
    s|S|y|Y|yes|YES|sim|SIM) ;;
    *) die "Installation cancelled before any package was changed" ;;
  esac
}

attempt_rollback() {
  (( ROLLBACK_READY )) || return 1
  local -a rollback_packages
  mapfile -d '' -t rollback_packages < <(find "$WORKDIR/rollback" -maxdepth 1 -type f -name '*.pkg.tar.zst' -print0 | sort -z)
  (( ${#rollback_packages[@]} > 0 )) || return 1

  info "SteamOS 7.2 installation failed; attempting to restore the cached previous Charcoal packages..."
  if run_privileged pacman -U --noconfirm "${rollback_packages[@]}"; then
    info "Previous Charcoal packages were restored from the local pacman cache."
    _update_grub || true
    return 0
  fi
  return 1
}

main() {
  require_command curl
  require_command python3
  require_command mktemp
  require_command pacman
  require_command awk
  require_command find
  require_command sort
  require_command steamos-readonly
  require_command steamos-devmode
  if (( EUID != 0 )); then
    require_command sudo
  fi

  WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/charcoal-72-installer.XXXXXX")"
  trap cleanup EXIT

  info "Fetching published Charcoal SteamOS 7.2 prereleases..."
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
    --output "$WORKDIR/releases.json" \
    "$RELEASES_API"

  local metadata
  metadata="$(parse_release_metadata "$WORKDIR/releases.json")" \
    || die "Could not identify a valid SteamOS 7.2 prerelease"

  local -a fields
  mapfile -t fields <<< "$metadata"
  (( ${#fields[@]} == 5 )) || die "Incomplete GitHub prerelease metadata"

  local release_tag=${fields[0]}
  local archive_name=${fields[1]}
  local archive_url=${fields[2]}
  local checksum_name=${fields[3]}
  local checksum_url=${fields[4]}
  local archive_path="$WORKDIR/$archive_name"
  local checksum_path="$WORKDIR/$checksum_name"
  local package_dir="$WORKDIR/packages"

  info "Downloading ${release_tag}..."
  download_file "$archive_url" "$archive_path"
  download_file "$checksum_url" "$checksum_path"

  info "Verifying release ZIP SHA-256..."
  verify_release_archive "$archive_path" "$checksum_path" "$archive_name"

  info "Extracting and verifying SteamOS 7.2 package SHA-256 checksums..."
  extract_and_verify_packages "$archive_path" "$package_dir"

  local -a packages
  mapfile -d '' -t packages < <(find "$package_dir" -maxdepth 1 -type f -name 'linux-charcoal-72-*.pkg.tar.zst' -print0 | sort -z)
  (( ${#packages[@]} == 2 )) || die "Verified prerelease does not contain exactly the kernel and headers packages"

  info "Preflighting package metadata with pacman before changing the system..."
  pacman -U --print --print-format '%n %v' "${packages[@]}" > "$WORKDIR/pacman-preflight.txt" \
    || die "pacman rejected the verified SteamOS 7.2 packages during preflight"

  local -a previous_packages
  mapfile -t previous_packages < <(list_installed_charcoal_packages "$WORKDIR/installed-packages.txt")
  capture_rollback_packages previous_packages
  confirm_transaction "$release_tag" "${previous_packages[@]}"

  info "Making SteamOS writable for the package transaction..."
  run_privileged steamos-readonly disable
  MADE_ROOT_WRITABLE=1

  info "Enabling SteamOS developer mode..."
  run_privileged steamos-devmode enable --no-prompt

  if (( ${#previous_packages[@]} )); then
    info "Removing previous Charcoal kernel packages without cascading dependency removal..."
    run_privileged pacman -Rdd --noconfirm "${previous_packages[@]}"
  fi

  info "Installing verified Charcoal SteamOS 7.2 prerelease ${release_tag}..."
  if ! run_privileged pacman -U --noconfirm "${packages[@]}"; then
    if attempt_rollback; then
      die "SteamOS 7.2 installation failed; the previous Charcoal packages were restored"
    fi
    die "SteamOS 7.2 installation failed after the previous Charcoal packages were removed; do not reboot until a working kernel is installed"
  fi

  info "Updating the bootloader configuration..."
  _update_grub

  info "Charcoal SteamOS 7.2 ${release_tag} was installed successfully. Reboot, then verify with: uname -r"
  info "ZRAM switches to LZ4 with ZSTD --fast=1 priority-1 recompression after booting Charcoal; the active swap is not reset during installation."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
