#!/usr/bin/env bash
# Install the newest Charcoal SteamOS 7.2 Preview release from the kernel-7.2 line.

set -Eeuo pipefail

readonly REPOSITORY="zarpon/linux-charcoal-vulcano"
readonly RELEASES_API="https://api.github.com/repos/${REPOSITORY}/releases?per_page=100"
readonly RELEASE_DOWNLOAD_PREFIX="https://github.com/${REPOSITORY}/releases/download/"
readonly RELEASE_TAG_PREFIX="charcoal-7.2-preview-"
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
  local url=$1 destination=$2
  curl --fail --silent --show-error --location \
    --proto '=https' --proto-redir '=https' --retry 3 --connect-timeout 15 \
    --output "$destination" "$url"
}

parse_release_metadata() {
  local releases_json=$1
  python3 - "$releases_json" "$REPOSITORY" "$RELEASE_DOWNLOAD_PREFIX" "$RELEASE_TAG_PREFIX" "$RELEASE_ZIP_PREFIX" <<'PY'
import json
import sys
from pathlib import PurePosixPath

releases_json, repository, download_prefix, tag_prefix, zip_prefix = sys.argv[1:]
with open(releases_json, encoding="utf-8") as handle:
    releases = json.load(handle)
if not isinstance(releases, list):
    raise SystemExit("GitHub did not return a releases list")

def text(value, label):
    if not isinstance(value, str) or not value or any(c in value for c in "\x00\r\n"):
        raise SystemExit(f"Invalid {label} in GitHub release response")
    return value

def checked_asset(asset, expected, tag):
    name = text(asset.get("name"), "asset name")
    url = text(asset.get("browser_download_url"), "asset URL")
    if name != expected:
        raise SystemExit(f"Unexpected asset name: {name}")
    if not url.startswith(f"{download_prefix}{tag}/"):
        raise SystemExit(f"Refusing asset outside {repository} release {tag}: {url}")
    return url

selected = None
for release in releases:
    if not isinstance(release, dict):
        continue
    tag = release.get("tag_name")
    if release.get("draft") or release.get("prerelease"):
        continue
    if isinstance(tag, str) and tag.startswith(tag_prefix):
        selected = release
        break
if selected is None:
    raise SystemExit("No published Charcoal SteamOS 7.2 Preview release was found")

tag = text(selected.get("tag_name"), "release tag")
assets = selected.get("assets")
if not isinstance(assets, list):
    raise SystemExit("GitHub 7.2 Preview release has no assets")
archives = [a for a in assets if isinstance(a, dict) and str(a.get("name", "")).startswith(zip_prefix) and str(a.get("name", "")).endswith(".zip")]
checksums = [a for a in assets if isinstance(a, dict) and a.get("name") == "RELEASE-ZIP-SHA256SUM"]
if len(archives) != 1 or len(checksums) != 1:
    raise SystemExit("7.2 Preview release assets are incomplete or ambiguous")
archive_name = text(archives[0].get("name"), "archive name")
if PurePosixPath(archive_name).name != archive_name:
    raise SystemExit("Invalid release ZIP filename")
print(tag)
print(archive_name)
print(checked_asset(archives[0], archive_name, tag))
print("RELEASE-ZIP-SHA256SUM")
print(checked_asset(checksums[0], "RELEASE-ZIP-SHA256SUM", tag))
PY
}

verify_release_archive() {
  local archive=$1 checksum_file=$2 archive_name=$3
  python3 - "$archive" "$checksum_file" "$archive_name" <<'PY'
import hashlib, re, sys
archive, checksum_file, archive_name = sys.argv[1:]
lines = open(checksum_file, encoding="utf-8").read().splitlines()
entries = []
for line in lines:
    m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
    if not m:
        raise SystemExit("Invalid RELEASE-ZIP-SHA256SUM format")
    entries.append((m.group(1).lower(), m.group(2)))
if len(entries) != 1 or entries[0][1] != archive_name:
    raise SystemExit("Release checksum does not match selected ZIP")
h = hashlib.sha256()
with open(archive, "rb") as f:
    for block in iter(lambda: f.read(1024 * 1024), b""):
        h.update(block)
if h.hexdigest() != entries[0][0]:
    raise SystemExit("Release ZIP SHA-256 verification failed")
PY
}

extract_and_verify_packages() {
  local archive=$1 destination=$2
  python3 - "$archive" "$destination" <<'PY'
import hashlib, re, stat, sys, zipfile
from pathlib import Path, PurePosixPath
archive, destination = map(Path, sys.argv[1:])
package_re = re.compile(r"^linux-charcoal-72(?:-headers)?-[^/\\\x00\r\n]+\.pkg\.tar\.zst$")
sum_re = re.compile(r"([0-9a-fA-F]{64}) [ *](linux-charcoal-72(?:-headers)?-[^/\\\x00\r\n]+\.pkg\.tar\.zst)")
with zipfile.ZipFile(archive) as zf:
    infos = zf.infolist()
    names = [i.filename for i in infos]
    if len(names) != len(set(names)) or "SHA256SUMS" not in names:
        raise SystemExit("Invalid release ZIP structure")
    package_infos = [i for i in infos if package_re.fullmatch(i.filename)]
    package_names = {i.filename for i in package_infos}
    if len(package_infos) != 2 or sum("-headers-" in n for n in package_names) != 1:
        raise SystemExit("Release ZIP must contain exactly kernel and headers packages")
    for info in package_infos:
        if PurePosixPath(info.filename).name != info.filename or stat.S_ISLNK(info.external_attr >> 16):
            raise SystemExit(f"Unsafe ZIP entry: {info.filename}")
    checksums = {}
    for line in zf.read("SHA256SUMS").decode("utf-8").splitlines():
        m = sum_re.fullmatch(line)
        if not m or m.group(2) in checksums:
            raise SystemExit("Invalid package SHA256SUMS")
        checksums[m.group(2)] = m.group(1).lower()
    if set(checksums) != package_names:
        raise SystemExit("Package list does not match SHA256SUMS")
    destination.mkdir(mode=0o700)
    for info in package_infos:
        target = destination / info.filename
        h = hashlib.sha256()
        with zf.open(info) as source, target.open("xb") as out:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                h.update(block); out.write(block)
        if h.hexdigest() != checksums[info.filename]:
            target.unlink(missing_ok=True)
            raise SystemExit(f"Package SHA-256 verification failed: {info.filename}")
PY
}

list_installed_packages() {
  pacman -Qq || die "Could not query installed packages"
}

select_installed_charcoal() {
  local installed_file=$1 name
  while IFS= read -r name; do
    [[ "$name" == linux-charcoal || "$name" == linux-charcoal-* ]] && printf '%s\n' "$name"
  done < "$installed_file"
}

select_stock_72() {
  local installed_file=$1 name
  while IFS= read -r name; do
    case "$name" in
      linux-neptune-72|linux-neptune-72-headers) printf '%s\n' "$name" ;;
    esac
  done < "$installed_file"
}

confirm_stock_removal() {
  local -n stock_ref=$1
  (( ${#stock_ref[@]} > 0 )) || return 0
  info "The stock SteamOS 7.2 kernel conflicts with linux-charcoal-72:"
  printf '  - %s\n' "${stock_ref[@]}"
  info "It must be removed before Charcoal 7.2 can be installed."

  if [[ "${CHARCOAL_72_REMOVE_STOCK:-0}" == "1" || "${CHARCOAL_72_ASSUME_YES:-0}" == "1" ]]; then
    return 0
  fi
  [[ -t 0 ]] || die "Stock kernel removal needs confirmation; rerun in a terminal or set CHARCOAL_72_REMOVE_STOCK=1"
  local answer
  read -r -p "Remove the SteamOS 7.2 stock kernel and continue? [s/N] " answer
  case "$answer" in
    s|S|y|Y|yes|YES|sim|SIM) return 0 ;;
    *) die "Installation cancelled; the stock kernel was not changed" ;;
  esac
}

confirm_transaction() {
  local release_tag=$1
  shift
  local -a previous=("$@")
  info "Verified 7.2 Preview release: ${release_tag}"
  if (( ${#previous[@]} )); then
    info "The following old kernel packages will be removed:"
    printf '  - %s\n' "${previous[@]}"
  fi
  info "The new kernel and headers are already downloaded and SHA-256 verified. The installer never reboots automatically."
  [[ "${CHARCOAL_72_ASSUME_YES:-0}" == "1" ]] && return 0
  [[ -t 0 ]] || die "Interactive confirmation is required; rerun in a terminal"
  local answer
  read -r -p "Continue with the Charcoal SteamOS 7.2 Preview installation? [s/N] " answer
  case "$answer" in
    s|S|y|Y|yes|YES|sim|SIM) ;;
    *) die "Installation cancelled before any package was changed" ;;
  esac
}

capture_rollback_packages() {
  local -n package_names=$1
  (( ${#package_names[@]} > 0 )) || return 0
  local rollback_dir="$WORKDIR/rollback" name version candidate found missing=0
  mkdir -p "$rollback_dir"
  for name in "${package_names[@]}"; do
    version="$(pacman -Q "$name" 2>/dev/null | awk '{print $2}')" || true
    [[ -n "$version" ]] || { missing=1; continue; }
    found=""
    for candidate in /var/cache/pacman/pkg/"${name}-${version}"-*.pkg.tar.zst; do
      [[ -f "$candidate" ]] && { found=$candidate; break; }
    done
    if [[ -n "$found" ]]; then
      cp -- "$found" "$rollback_dir/"
    else
      missing=1
    fi
  done
  if (( missing == 0 )); then
    ROLLBACK_READY=1
  else
    info "warning: not every removed kernel package is present in pacman's cache; automatic rollback may be unavailable."
  fi
}

attempt_rollback() {
  (( ROLLBACK_READY )) || return 1
  local -a rollback_packages
  mapfile -d '' -t rollback_packages < <(find "$WORKDIR/rollback" -maxdepth 1 -type f -name '*.pkg.tar.zst' -print0 | sort -z)
  (( ${#rollback_packages[@]} > 0 )) || return 1
  info "Installation failed; attempting to restore the previous kernel packages from pacman cache..."
  if run_privileged pacman -U --noconfirm "${rollback_packages[@]}"; then
    _update_grub || true
    return 0
  fi
  return 1
}

main() {
  for cmd in curl python3 mktemp pacman awk find sort steamos-readonly steamos-devmode; do require_command "$cmd"; done
  (( EUID == 0 )) || require_command sudo
  WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/charcoal-72-installer.XXXXXX")"
  trap cleanup EXIT

  info "Fetching published Charcoal SteamOS 7.2 Preview releases..."
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --retry 3 --connect-timeout 15 --header 'Accept: application/vnd.github+json' \
    --header 'X-GitHub-Api-Version: 2022-11-28' --user-agent "$USER_AGENT" \
    --output "$WORKDIR/releases.json" "$RELEASES_API"

  local metadata
  metadata="$(parse_release_metadata "$WORKDIR/releases.json")" || die "Could not identify a valid SteamOS 7.2 Preview release"
  local -a fields
  mapfile -t fields <<< "$metadata"
  (( ${#fields[@]} == 5 )) || die "Incomplete GitHub 7.2 Preview release metadata"

  local release_tag=${fields[0]} archive_name=${fields[1]} archive_url=${fields[2]}
  local checksum_name=${fields[3]} checksum_url=${fields[4]}
  local archive_path="$WORKDIR/$archive_name" checksum_path="$WORKDIR/$checksum_name" package_dir="$WORKDIR/packages"

  info "Downloading ${release_tag}..."
  download_file "$archive_url" "$archive_path"
  download_file "$checksum_url" "$checksum_path"
  info "Verifying release ZIP SHA-256..."
  verify_release_archive "$archive_path" "$checksum_path" "$archive_name"
  info "Extracting and verifying SteamOS 7.2 packages..."
  extract_and_verify_packages "$archive_path" "$package_dir"

  local -a packages
  mapfile -d '' -t packages < <(find "$package_dir" -maxdepth 1 -type f -name 'linux-charcoal-72-*.pkg.tar.zst' -print0 | sort -z)
  (( ${#packages[@]} == 2 )) || die "Verified release does not contain exactly kernel and headers"

  info "Checking package metadata without starting a transaction..."
  local pkg pkgname
  for pkg in "${packages[@]}"; do
    pkgname="$(pacman -Qp "$pkg" | awk '{print $1}')" || die "pacman could not read package metadata: $pkg"
    [[ "$pkgname" == linux-charcoal-72 || "$pkgname" == linux-charcoal-72-headers ]] \
      || die "Unexpected package in release: $pkgname"
  done

  local installed_file="$WORKDIR/installed-packages.txt"
  list_installed_packages > "$installed_file"
  local -a previous_charcoal stock_packages remove_packages
  mapfile -t previous_charcoal < <(select_installed_charcoal "$installed_file")
  mapfile -t stock_packages < <(select_stock_72 "$installed_file")

  confirm_stock_removal stock_packages
  remove_packages=("${previous_charcoal[@]}" "${stock_packages[@]}")
  capture_rollback_packages remove_packages
  confirm_transaction "$release_tag" "${remove_packages[@]}"

  info "Making SteamOS writable for the package transaction..."
  run_privileged steamos-readonly disable
  MADE_ROOT_WRITABLE=1
  info "Enabling SteamOS developer mode..."
  run_privileged steamos-devmode enable --no-prompt

  if (( ${#remove_packages[@]} )); then
    info "Removing conflicting/previous kernel packages without cascading dependency removal..."
    run_privileged pacman -Rdd --noconfirm "${remove_packages[@]}"
  fi

  info "Installing verified Charcoal SteamOS 7.2 Preview ${release_tag}..."
  if ! run_privileged pacman -U --noconfirm "${packages[@]}"; then
    if attempt_rollback; then
      die "SteamOS 7.2 installation failed; previous kernel packages were restored"
    fi
    die "SteamOS 7.2 installation failed after kernel removal; do not reboot until a working kernel is installed"
  fi

  info "Updating the bootloader configuration..."
  _update_grub
  info "Charcoal SteamOS 7.2 Preview ${release_tag} installed successfully. Reboot, then verify with: uname -r"
  info "ZRAM switches to LZ4 with ZSTD --fast=1 priority-1 recompression after booting Charcoal; active swap is not reset during installation."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
