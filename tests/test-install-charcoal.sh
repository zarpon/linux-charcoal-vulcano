#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly INSTALLER="$REPO_ROOT/install-charcoal.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() {
  printf 'test failure: %s\n' "$*" >&2
  exit 1
}

bash -n "$INSTALLER" || fail "installer shell syntax is invalid"

# Source functions without running main().
# shellcheck source=/dev/null
source "$INSTALLER"

cat > "$tmp/installed" <<'EOF'
linux-charcoal-616
linux-charcoal-616-headers
linux-neptune-72
linux-neptune-72-headers
unrelated-package
EOF

mapfile -t stock < <(select_stock_72 "$tmp/installed")
[[ ${#stock[@]} -eq 2 ]] || fail "expected stock kernel and stock headers"
[[ ${stock[0]} == linux-neptune-72 ]] || fail "stock kernel was not detected"
[[ ${stock[1]} == linux-neptune-72-headers ]] || fail "stock headers were not detected"

mapfile -t old_charcoal < <(select_installed_charcoal "$tmp/installed")
[[ ${#old_charcoal[@]} -eq 2 ]] || fail "previous Charcoal packages were not detected"

# Automatic mode used by CI must explicitly authorize stock removal.
CHARCOAL_72_REMOVE_STOCK=1 confirm_stock_removal stock

# Non-interactive execution without authorization must refuse to remove stock.
if ( CHARCOAL_72_REMOVE_STOCK=0 CHARCOAL_72_ASSUME_YES=0 confirm_stock_removal stock >/dev/null 2>&1 ); then
  fail "installer removed stock kernel without explicit authorization"
fi

# No stock kernel means no removal confirmation is required.
empty_stock=()
confirm_stock_removal empty_stock

# Regression checks for the real transaction order and prompt.
grep -Fq 'Remove the SteamOS 7.2 stock kernel and continue? [s/N]' "$INSTALLER" \
  || fail "interactive stock-kernel removal prompt is missing"
grep -Fq 'linux-neptune-72|linux-neptune-72-headers' "$INSTALLER" \
  || fail "installer is not limited to the SteamOS 7.2 stock kernel packages"
grep -Fq 'remove_packages=("${previous_charcoal[@]}" "${stock_packages[@]}")' "$INSTALLER" \
  || fail "stock packages are not included in the removal transaction"
grep -Fq 'run_privileged pacman -Rdd --noconfirm "${remove_packages[@]}"' "$INSTALLER" \
  || fail "installer does not remove approved conflicting kernel packages"
grep -Fq 'run_privileged pacman -U --noconfirm "${packages[@]}"' "$INSTALLER" \
  || fail "installer does not install verified Charcoal packages"

remove_line="$(grep -n -F 'run_privileged pacman -Rdd --noconfirm "${remove_packages[@]}"' "$INSTALLER" | head -n1 | cut -d: -f1)"
install_line="$(grep -n -F 'run_privileged pacman -U --noconfirm "${packages[@]}"' "$INSTALLER" | head -n1 | cut -d: -f1)"
[[ -n "$remove_line" && -n "$install_line" && $remove_line -lt $install_line ]] \
  || fail "stock removal must occur before Charcoal installation"

grep -Fq 'RELEASE_TAG_PREFIX="charcoal-7.2-preview-"' "$INSTALLER" \
  || fail "installer is not pinned to the 7.2 Preview release channel"
grep -Fq 'release.get("prerelease")' "$INSTALLER" \
  || fail "installer must reject GitHub prereleases"

printf 'install-charcoal SteamOS 7.2 stock-removal tests passed\n'
