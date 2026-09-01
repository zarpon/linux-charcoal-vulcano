#!/usr/bin/env bash

set -Eeuo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly INSTALLER="$REPO_ROOT/install-charcoal.sh"
readonly BASH_BIN="$(command -v bash)"

test_root="$(mktemp -d)"
fixture_dir="$test_root/fixture"
bin_dir="$test_root/bin"
log_file="$test_root/commands.log"

cleanup() {
  rm -rf -- "$test_root"
}
trap cleanup EXIT

fail() {
  printf 'test failure: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  local expected=$1
  grep -F -- "$expected" "$log_file" >/dev/null || fail "expected log entry: $expected"
}

assert_not_contains() {
  local unexpected=$1
  if grep -F -- "$unexpected" "$log_file" >/dev/null; then
    fail "unexpected log entry: $unexpected"
  fi
}

assert_precedes() {
  local before=$1
  local after=$2
  local before_line after_line
  before_line="$(grep -n -m 1 -F -- "$before" "$log_file" || true)"
  after_line="$(grep -n -m 1 -F -- "$after" "$log_file" || true)"
  [[ -n "$before_line" ]] || fail "missing log entry: $before"
  [[ -n "$after_line" ]] || fail "missing log entry: $after"
  before_line=${before_line%%:*}
  after_line=${after_line%%:*}
  (( before_line < after_line )) || fail "expected '$before' before '$after'"
}

make_fixture() {
  local build_dir="$fixture_dir/build"
  local kernel_package="linux-charcoal-72-7.2.0.valve1.cc1-1-x86_64.pkg.tar.zst"
  local headers_package="linux-charcoal-72-headers-7.2.0.valve1.cc1-1-x86_64.pkg.tar.zst"

  mkdir -p "$build_dir" "$bin_dir"
  printf 'kernel fixture\n' > "$build_dir/$kernel_package"
  printf 'headers fixture\n' > "$build_dir/$headers_package"

  python3 - "$fixture_dir" "$build_dir" "$kernel_package" "$headers_package" <<'PY'
import hashlib
import json
import sys
import zipfile
from pathlib import Path

fixture = Path(sys.argv[1])
build = Path(sys.argv[2])
kernel = sys.argv[3]
headers = sys.argv[4]
checksums = []
for name in (kernel, headers):
    digest = hashlib.sha256((build / name).read_bytes()).hexdigest()
    checksums.append(f"{digest}  {name}\n")
manifest = "".join(checksums)
archive = fixture / "linux-charcoal-72-test-r1.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("SHA256SUMS", manifest)
    zf.write(build / kernel, kernel)
    zf.write(build / headers, headers)

digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(fixture / "RELEASE-ZIP-SHA256SUM").write_text(
    f"{digest}  {archive.name}\n", encoding="utf-8"
)
(fixture / "BAD-RELEASE-ZIP-SHA256SUM").write_text(
    f"{'0' * 64}  {archive.name}\n", encoding="utf-8"
)
releases = [
    {
        "tag_name": "charcoal-6.16-stable-like",
        "draft": False,
        "prerelease": False,
        "assets": [],
    },
    {
        "tag_name": "charcoal-7.2-preview-rejected-prerelease",
        "draft": False,
        "prerelease": True,
        "assets": [],
    },
    {
        "tag_name": "charcoal-7.2-preview-test-r1",
        "name": "Charcoal 7.2 Preview",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": archive.name,
                "browser_download_url": "https://github.com/zarpon/linux-charcoal-vulcano/releases/download/charcoal-7.2-preview-test-r1/" + archive.name,
            },
            {
                "name": "RELEASE-ZIP-SHA256SUM",
                "browser_download_url": "https://github.com/zarpon/linux-charcoal-vulcano/releases/download/charcoal-7.2-preview-test-r1/RELEASE-ZIP-SHA256SUM",
            },
        ],
    },
]
(fixture / "releases.json").write_text(json.dumps(releases), encoding="utf-8")
PY
}

write_fake_commands() {
  printf '%s\n' \
    "#!$BASH_BIN" \
    'set -Eeuo pipefail' \
    'output=""' \
    'url=""' \
    'while (($#)); do' \
    '  case "$1" in' \
    '    --output|-o) output="$2"; shift 2 ;;' \
    '    *) url="$1"; shift ;;' \
    '  esac' \
    'done' \
    '[[ -n "$output" ]] || exit 2' \
    'case "$url" in' \
    '  "https://api.github.com/repos/zarpon/linux-charcoal-vulcano/releases?per_page=100")' \
    '    cp "$CHARCOAL_TEST_FIXTURE/releases.json" "$output" ;;' \
    '  https://github.com/zarpon/linux-charcoal-vulcano/releases/download/charcoal-7.2-preview-test-r1/linux-charcoal-72-test-r1.zip)' \
    '    cp "$CHARCOAL_TEST_FIXTURE/linux-charcoal-72-test-r1.zip" "$output" ;;' \
    '  https://github.com/zarpon/linux-charcoal-vulcano/releases/download/charcoal-7.2-preview-test-r1/RELEASE-ZIP-SHA256SUM)' \
    '    if [[ "${CHARCOAL_TEST_SCENARIO:-normal}" == "bad-checksum" ]]; then' \
    '      cp "$CHARCOAL_TEST_FIXTURE/BAD-RELEASE-ZIP-SHA256SUM" "$output"' \
    '    else' \
    '      cp "$CHARCOAL_TEST_FIXTURE/RELEASE-ZIP-SHA256SUM" "$output"' \
    '    fi ;;' \
    '  *) exit 3 ;;' \
    'esac' \
    > "$bin_dir/curl"

  printf '%s\n' \
    "#!$BASH_BIN" \
    'exec "$@"' \
    > "$bin_dir/sudo"

  printf '%s\n' \
    "#!$BASH_BIN" \
    'printf "steamos-readonly %s\\n" "$*" >> "$CHARCOAL_TEST_LOG"' \
    > "$bin_dir/steamos-readonly"

  printf '%s\n' \
    "#!$BASH_BIN" \
    'printf "steamos-devmode %s\\n" "$*" >> "$CHARCOAL_TEST_LOG"' \
    > "$bin_dir/steamos-devmode"

  printf '%s\n' \
    "#!$BASH_BIN" \
    'set -Eeuo pipefail' \
    'case "${1:-}" in' \
    '  -Qq)' \
    '    if [[ "${CHARCOAL_TEST_SCENARIO:-normal}" != "no-old" ]]; then' \
    '      printf "%s\\n" linux-charcoal-616 linux-charcoal-616-headers linux-neptune-72 unrelated-package' \
    '    else' \
    '      printf "%s\\n" linux-neptune-72 unrelated-package' \
    '    fi ;;' \
    '  -Q)' \
    '    case "${2:-}" in' \
    '      linux-charcoal-616) printf "%s\\n" "linux-charcoal-616 6.16.12-1" ;;' \
    '      linux-charcoal-616-headers) printf "%s\\n" "linux-charcoal-616-headers 6.16.12-1" ;;' \
    '      *) exit 1 ;;' \
    '    esac ;;' \
    '  -U)' \
    '    if [[ " $* " == *" --print "* ]]; then' \
    '      printf "%s\\n" "linux-charcoal-72 test" "linux-charcoal-72-headers test"' \
    '      exit 0' \
    '    fi' \
    '    printf "pacman %s\\n" "$*" >> "$CHARCOAL_TEST_LOG"' \
    '    [[ "${CHARCOAL_TEST_SCENARIO:-normal}" != "install-failure" ]] || exit 9 ;;' \
    '  -Rdd)' \
    '    printf "pacman %s\\n" "$*" >> "$CHARCOAL_TEST_LOG"' \
    '    [[ "${CHARCOAL_TEST_SCENARIO:-normal}" != "remove-failure" ]] || exit 8 ;;' \
    '  *) exit 4 ;;' \
    'esac' \
    > "$bin_dir/pacman"

  printf '%s\n' \
    "#!$BASH_BIN" \
    'printf "grub-mkconfig %s\\n" "$*" >> "$CHARCOAL_TEST_LOG"' \
    > "$bin_dir/grub-mkconfig"

  chmod +x "$bin_dir"/*
}

run_installer() {
  local scenario=$1
  PATH="$bin_dir:$PATH" \
    CHARCOAL_TEST_FIXTURE="$fixture_dir" \
    CHARCOAL_TEST_LOG="$log_file" \
    CHARCOAL_TEST_SCENARIO="$scenario" \
    CHARCOAL_72_ASSUME_YES=1 \
    bash "$INSTALLER"
}

make_fixture
write_fake_commands

grep -Fq 'RELEASE_TAG_PREFIX="charcoal-7.2-preview-"' "$INSTALLER" \
  || fail 'installer is not pinned to the SteamOS 7.2 Preview tag prefix'
grep -Fq 'or release.get("prerelease")' "$INSTALLER" \
  || fail 'installer does not reject GitHub prereleases from the 7.2 Preview channel'
grep -Fq 'linux-charcoal-72' "$INSTALLER" \
  || fail 'installer is not pinned to SteamOS 7.2 package names'

: > "$log_file"
run_installer normal >/dev/null
assert_contains 'steamos-readonly disable'
assert_contains 'steamos-devmode enable --no-prompt'
assert_contains 'pacman -Rdd --noconfirm linux-charcoal-616 linux-charcoal-616-headers'
assert_contains 'pacman -U --noconfirm '
assert_contains 'linux-charcoal-72-7.2.0.valve1.cc1-1-x86_64.pkg.tar.zst'
assert_contains 'linux-charcoal-72-headers-7.2.0.valve1.cc1-1-x86_64.pkg.tar.zst'
assert_contains 'grub-mkconfig -o /boot/grub/grub.cfg'
assert_contains 'steamos-readonly enable'
assert_not_contains 'linux-neptune-72 unrelated-package'
assert_precedes 'pacman -Rdd --noconfirm' 'pacman -U --noconfirm'
assert_precedes 'pacman -U --noconfirm' 'grub-mkconfig -o /boot/grub/grub.cfg'

: > "$log_file"
run_installer no-old >/dev/null
assert_not_contains 'pacman -Rdd'
assert_contains 'pacman -U --noconfirm '

: > "$log_file"
if run_installer bad-checksum >/dev/null 2>&1; then
  fail 'installer accepted a 7.2 Preview ZIP with an invalid checksum'
fi
assert_not_contains 'steamos-readonly disable'
assert_not_contains 'pacman -Rdd'
assert_not_contains 'pacman -U --noconfirm'

: > "$log_file"
if run_installer remove-failure >/dev/null 2>&1; then
  fail 'installer continued after failure to remove the previous Charcoal packages'
fi
assert_contains 'pacman -Rdd --noconfirm'
assert_not_contains 'pacman -U --noconfirm '
assert_contains 'steamos-readonly enable'

printf 'install-charcoal SteamOS 7.2 Preview tests passed\n'
