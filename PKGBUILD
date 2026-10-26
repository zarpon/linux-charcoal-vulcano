# Maintainer: Thomas Rohloff <v10lator@myway.de>
# Maintainer: John Schoenick <johns@valvesoftware.com>
# Maintainer: Jan Alexander Steffens (heftig) <heftig@archlinux.org>

pkgbase=linux-charcoal-72
_nepbase=linux-neptune-72
_tag=7.2.7-valve2
_ver=2
pkgver=${_tag//-/.}.cc$_ver
pkgrel=1
pkgdesc='Linux'
url="https://gitlab.steamos.cloud/jupiter/linux-integration/-/tree/$_tag"
arch=(x86_64)
license=(GPL-2.0-only)
makedepends=(
  bc
  cpio
  gettext
  libelf
  pahole
  perl
  python
  tar
  xz

  # htmldocs
  # Jupiter: documentation dependencies, disabled for now
  #graphviz
  #imagemagick
  #python-sphinx
  #python-yaml
  #texlive-latexextra

  # Jupiter: we're using git+ssh for the source
  git
  openssh

  # Charcoal: We build on LLVM
  llvm
  clang
  ccache
  lld
)
options=(
  !debug
  !strip
)

# Charcoal: use ccache when available without making it mandatory for local builds.
_ccache_prefix=
if command -v ccache >/dev/null 2>&1; then
  _ccache_prefix='ccache '
fi

_make_llvm() {
  make LLVM=1 \
    CC="${_ccache_prefix}clang" \
    HOSTCC="${_ccache_prefix}clang" \
    HOSTCXX="${_ccache_prefix}clang++" \
    "$@"
}
_srcname=archlinux-linux-charcoal
# Refreshed before every CI build; for local builds run:
# python3 automation/resolve-controller-drivers.py --write
_xpadneo_version=0.10.5
source=(
  "$_srcname::git+https://github.com/evlaV/linux-integration.git#tag=$_tag"
  config          # Upstream Arch Linux kernel configuration file, DO NOT EDIT!!!
  config-neptune  # Jupiter: the neptune kernel fragment file (overrides 'config' above)
  config-charcoal # Charcoal: The Charcoal kernel fragment file
  charcoal.conf
  99-charcoal-sysctl.conf
  99-charcoal-memory.conf
  99-charcoal-gaming.conf
  65-adios.rules
  60-charcoal-zram-ir.rules
  configure-zram-ir
  configure-gaming-swap
  gaming-zswap.service
  gaming-swap.install
  nap-tools.tar.gz
  90-charcoal-zram.conf
  90-charcoal-zram-ir.conf
  99-charcoal.sh
  vangogh_allow_higher_cpu_freq.patch
  vangogh_higher_max_power_limit.patch
  latest-lru_marie.patch
  latest-zram-ir.patch
  latest-amd-pstate-epp-boost-01-kernel-doc.patch
  latest-amd-pstate-epp-boost-02-cache-order.patch
  latest-amd-pstate-epp-boost-03-core.patch
  latest-amd-pstate-epp-boost-04-docs.patch
  ryzen_smu.diff
  xpad-noone.diff
  latest-clear.patch
  latest-o3.patch
  latest-libbpf-uninitialized.patch
  latest-cpu-optimizations.patch
  latest-dkms-clang.patch
  latest-clang-polly.patch
  latest-firmware-name.patch
  latest-minstrel-frac.patch
  latest-minstrel-fluctuation.patch
  latest-minstrel-downgrade.patch
  latest-ath11k-remapped-ce.patch
  latest-bore.patch
  latest-bore-sched-ext-coexistence-fix.patch
   latest-poc-selector.patch
  latest-adios.patch
  latest-adios-default.patch
  latest-zen-01.patch
  latest-zen-02.patch
  "git+https://github.com/amkillam/ryzen_smu.git#commit=9f9569f889935f7c7294cc32c1467e5a4081701a"
  "git+https://github.com/dlundqvist/xone.git#commit=f2aa9fe01103d7600553b505b298ff0bd47ff280"
  "git+https://github.com/forkymcforkface/xpad-noone.git#commit=a52e32cf182435d608e66bef9a6c89ebac891999"
  "git+https://github.com/atar-axis/xpadneo.git#commit=e8f103a77f777c2c54536dd947969cf228699c13"
  latest-nap.patch
  iommu-perfopt-consolidado-v3.patch
  zstd-crypto-default-level-1.patch
)
sha256sums=(
  'SKIP'
  'ecd8c76eb203493e67ba4052e7bc1fa46f51c91566f102172e7a18d7de2dd5eb'
  'c9482d23e18ab37911847918eadfbc022c606f8eddab07acd43ef4d4f339037f'
  '59a12e3c7d7511cd27a5e5fd9f46e97d62d16be4e6762cd1d15d25a8f4de47f5'
  'b831de1b98a2f77f636f4780e37ebfcb3a6829f94f5423eb04c4b26e64ac43b8'
  '0ca1dd4b6dead2d5cfd40bab0917fec763693c9bebec9ebf33d8b48f90ba0a1b'
  'ae521b7acee1c4fcd46cc7fb2d514782a3b74b475115ca4f5c59c804f3f0c3f6'
  '6e71f4ef06f4e40053ac530d0000669bcf65db6e3992ccee54f0c61f8ba04ec6'
  '52cbbf41450806d766260bc4f1ea055f6f9fdd55d37ad831840b16d505beb0cc'
  '35fc7647671b1ab412804143a0585dde8d9880097c06feb520f90680780ac5e5'
  '3e200a7ad9661f59be2dfd442fd993fd130da8a6f5df7d8b4ec40d86351b1dcd'
  'e5c51e656e4425721f8d491318328f0e3127fd982cd0fa4efded59bee80a6a35'
  '4ac7cdcd2efdcd5fda021eefa670166832bbb493ea7b33f6e66eca1a67cb4e31'
  '8e4738f3aaa22832b3e45dca7b226460702e88bcdcd026ea5d5062e5aa0444de'
  '58c97868ab414a9600e59a5c170dc44803b49fe07a10f7a4497076ae7ca6ffac'
  'b59543c9aac43412e8b90b050380f482214ab33c4703d621ff0ea91ea39c6761'
  '07068c432fd7e80689f44a28346f1909de9ee77aa3e72dfaa6a4ea89d9921afd'
  '1f7df01db0bcd7c18230878003466ac3f651f8f21e74323b7e8178871d824f74'
  '1a6f9d691612c4a729032273199d17756dd6666d85019655bd95ea24eff59cac'
  '1c49146dc5878bfab32b331d11cb66d493670bbe590ff07c2050305911c281c3'
  '383b8cea61ef133ec2dfeb9fd1b4f1f8e55b2649cd41e1aee9d71fd8aaaaf4ea'
  '3371e21a20c5e2a0c619984e8722b6b420f0664cacfdf65de51295176fed7ff2'
  '74f02a5cd603afe2b714a7cccff92a715b25a643af51f3d66c959a0724e78bae'
  '9b5caecdd70729103f04f6ec5b3e1aa8a05d91bbf79b97ad050c10c8dbb5fbe1'
  '991cd0df7c2fabcef05e2009eb833b6087a6a3f5d1b11fc9d1f027192e131162'
  '6ff36ba97524ce21a8b8a9e127f37c8fe1016f6a2b10ca439d2705539630d096'
  '51ad35f817863e2222e74a093b5d10be77089d4a6e8749b2f44839f380ec0c7f'
  'ff3bbe78d6f072d57f567878e870956242ee78ccddd258b1ec2e4729621138fe'
  '2c9843a51e8dd4b41f7620dcc4bf3677c7867d922073202c095324fb1443cfa5'
  '492aafbd940b18b817e4b7957805b9874f488cc1463fee588dd8dacd18c86677'
  'f573edc1cb722c34b18a62db5d04c7488d6250807e694a691382b487c48d4445'
  'f2b896c609c672c68c47639028b1d51a2beab2c84256c0c37807142857b62763'
  '6f45ef083841792e88fbadbfefb0630abd738a131f9782333fbc61f8b6712b4b'
  'ecb48f8b4a122180e815beff3f64fd3077fb8bfb57ff2c554c1e8e31388eb8e9'
  'd787273bd3d00279c38127e3f4928d1685dea070f2152e75f08754e63ef1ba0f'
  'bf2186776d96122136019b7b11aea1f0f46914bf107aa83c949e654290f7eed3'
  '78da5c2c011b2679f1309366c3964a919607db5fa1b76a3e426c5af67eded5a1'
  '4929f7a8033f34715c2a19b606c45d0d711e7328452ed1b31a5bf52a0c1a7232'
  '6a2290d4edd8852c43dbb0ebc5c6c95bdaa92dd5ca4dcd22ccbe4cd9d3d07819'
  '948aa495364332596d9f00fba1f90b2da04676a37faaeab9ef2390c44c7fbd83'
  'cdf138cdb94fcb4e2988bd7d2873a51522fdb7212ec314fde202facaf8210b5c'
  'a2bab701202fc4d5459e46f3b5136dca3ac8902d5f534c6d57435d811b273e80'
  '4f186fa06bfb0e0e08320cb53a38afebe6d9eaa5c820396015c59f993bf8e1b6'
  '5ef2f14326a5fab8980d1ebb6734ece576f930c173b4980eb026513aa3b1b9d0'
  'bc647f73ec860a0fe7d074c2377588816a616dc2a651b30d7b9cd168863a17c6'
  '5059762e54c8dbe4262d48eafb8d486a54244eec71da5d7b61fc0f5f1c5c2ea7'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  '4d4ac50ba014de33638a2efe9c6adc507b888c6d090aa29ea17b2a4686de4e07'
  '52ee747b6888f6e59df2cc6a4b6d6ccbc104c932bc8cb11b1ff0035cde47425a'
  '8c35a18407440f543518e383a96f8098438c3cbe4ea034241fb9a7fe8f7be129'
)
export KBUILD_BUILD_HOST=archlinux
export KBUILD_BUILD_USER=$pkgbase
export KBUILD_BUILD_TIMESTAMP="$(date -Ru${SOURCE_DATE_EPOCH:+d @$SOURCE_DATE_EPOCH})"

_validate_kernel_config() {
  local expected
  for expected in \
    'CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE_O3=y' \
    'CONFIG_ZEN_INTERACTIVE=y' \
    'CONFIG_ZSWAP=y' \
    'CONFIG_ZSWAP_DEFAULT_ON=y' \
    'CONFIG_ZSWAP_SHRINKER_DEFAULT_ON=y' \
    'CONFIG_ZSWAP_COMPRESSOR_DEFAULT_ZSTD=y' \
    'CONFIG_ZSWAP_COMPRESSOR_DEFAULT="zstd"' \
    'CONFIG_ZSMALLOC=y' \
    'CONFIG_CRYPTO_LZ4=y'; do
    if ! grep -qxF "$expected" .config; then
      echo "ERROR: kernel configuration requires $expected after olddefconfig" >&2
      return 1
    fi
  done
}

prepare() {
  # Always resolve current upstream tools, including local makepkg builds.
  python3 "$startdir/nap-tools/refresh-tools.py" \
    --output "$srcdir/nap-tools-latest" --record "$startdir/logs/nap-tools-upstream.json"
  NAP_TOOLS_TEST_SOURCE_DIR="$srcdir/nap-tools-latest" \
    python3 "$startdir/tests/test_nap_tools.py"
  cd $_srcname

  echo "Setting version..."
  echo "-$pkgrel" > localversion.10-pkgrel
  echo "${pkgbase#linux}" > localversion.20-pkgname

  local src
  for src in "${source[@]}"; do
    src="${src%%::*}"
    src="${src##*/}"
    src="${src%.zst}"
    [[ $src = *.patch ]] || continue
    echo "Applying patch $src..."
    if [[ $src == latest-poc-selector.patch ]]; then
      local adapted_poc="../${src%.patch}-valve-port.patch"
      python3 "$startdir/automation/port-poc-selector.py" \
        "../$src" "$adapted_poc" kernel/sched/sched.h kernel/sched/fair.c
      git apply --check "$adapted_poc"
      git apply "$adapted_poc"
    elif [[ $src == latest-adios.patch ]]; then
      local adapted_adios="../${src%.patch}-7.2-port.patch"
      python3 "$startdir/automation/port-adios-7.2.py" \
        "../$src" "$adapted_adios" block/elevator.c
      git apply --check "$adapted_adios"
      git apply "$adapted_adios"
    elif [[ $src == latest-zen-02.patch ]]; then
      python3 "$startdir/automation/port-zen-cpufreq-7.2.py" \
        "../$src" drivers/cpufreq/Kconfig.x86
      git diff --check -- drivers/cpufreq/Kconfig.x86
    elif [[ $src == latest-libbpf-uninitialized.patch ]]; then
      patch -Np1 < "../$src"
      python3 "$startdir/automation/fix-libbpf-clang-warning.py" \
        tools/lib/bpf/elf.c
    else
      patch -Np1 < "../$src"
    fi
  done

  python3 "$startdir/automation/fix-gud-tv-mode-fortify.py" \
    drivers/gpu/drm/gud/gud_connector.c
  git diff --check -- drivers/gpu/drm/gud/gud_connector.c

  python3 "$startdir/automation/fix-nap-kernel-api.py" \
    drivers/cpuidle/governors/nap/nap.c
  git diff --check -- drivers/cpuidle/governors/nap/nap.c

  python3 "$startdir/automation/configure-zen-interactive.py" "$PWD"

  # This Crypto API default feeds both compression parameters and workspace
  # allocation. Fail before compiling if source changes stop applying it.
  grep -Eq '^#define[[:space:]]+ZSTD_DEF_LEVEL[[:space:]]+1([[:space:]]|$)' crypto/zstd.c
  sha256sum crypto/zstd.c | tee "$startdir/logs/zstd-crypto-source.sha256"
  grep -E '^#define[[:space:]]+ZSTD_DEF_LEVEL[[:space:]]+' crypto/zstd.c \
    | tee "$startdir/logs/zstd-crypto-level.txt"

  echo "Setting config..."
  cp ../config .config
  scripts/kconfig/merge_config.sh -m ../config ../config-neptune ../config-charcoal # Charcoal: merge the extra fragment
  _make_llvm olddefconfig
  _validate_kernel_config
  diff -u ../config .config || :

  _make_llvm -s kernelrelease > version

  # Charcoal patches for DKMS modules
  cd ../ryzen_smu
  patch -Np1 < ../ryzen_smu.diff
  cd ../xpad-noone
  patch -Np1 < ../xpad-noone.diff

  echo "Prepared $pkgbase version $(<../$_srcname/version)"
}

build() {
  cd $_srcname
  _make_llvm all
  _make_llvm -C tools/bpf/bpftool vmlinux.h feature-clang-bpf-co-re=1
#  make htmldocs # Jupiter: Don't build the docs

  # Charcoal: Build bundles DKMS modules
  _make_llvm M=../ryzen_smu modules
  _make_llvm M=../xone modules
  _make_llvm M=../xpad-noone modules
  _make_llvm M=../xpadneo/hid-xpadneo/src VERSION=$_xpadneo_version modules
}

_package() {
  install=gaming-swap.install
  pkgdesc="The $pkgdesc kernel and modules"
  depends=(
    coreutils
    initramfs
    kmod
    python
    util-linux
    systemd
    btrfs-progs
  )
  optdepends=(
    'wireless-regdb: to set the correct wireless channels of your country'
    'linux-firmware: firmware images needed for some devices'
  )
  provides=(
    KSMBD-MODULE
    VIRTUALBOX-GUEST-MODULES
    WIREGUARD-MODULE
    ryzen_smu
    xone
    xpad-noone
    xpadneo
    $_nepbase
  )
  replaces=(
    virtualbox-guest-modules-arch
    wireguard-arch
    ryzen_smu
    xone
    xpad-noone
    xpadneo
    $_nepbase
  )
  conflicts=(
    $_nepbase
  )

  cd $_srcname
  local modulesdir="$pkgdir/usr/lib/modules/$(<version)"

  echo "Installing boot image..."
  # systemd expects to find the kernel here to allow hibernation
  # https://github.com/systemd/systemd/commit/edda44605f06a41fb86b7ab8128dcf99161d2344
  install -Dm644 "$(_make_llvm -s image_name)" "$modulesdir/vmlinuz"

  # Used by mkinitcpio to name the kernel
  echo "$_nepbase" | install -Dm644 /dev/stdin "$modulesdir/pkgbase"

  echo "Installing modules..."
  ZSTD_CLEVEL=19 _make_llvm INSTALL_MOD_PATH="$pkgdir/usr" INSTALL_MOD_STRIP=1 \
    DEPMOD=/doesnt/exist modules_install  # Suppress depmod

  # Charcoal: Install modprobe file (currently workaround for xpadneo)
  install -D -m 0644 -t "$pkgdir/etc/modprobe.d" ../charcoal.conf
  # Charcoal: Install environment file (currently workaround for xpadneo)
  install -D -m 0644 -t "$pkgdir/etc/profile.d" ../99-charcoal.sh
  # Charcoal: persistent runtime defaults for SteamOS sessions and kernel memory.
  install -D -m 0644 ../99-charcoal-sysctl.conf \
    "$pkgdir/usr/lib/sysctl.d/99-charcoal.conf"
  install -D -m 0644 ../99-charcoal-memory.conf \
    "$pkgdir/usr/lib/tmpfiles.d/99-charcoal-memory.conf"
  install -D -m 0644 ../99-charcoal-gaming.conf \
    "$pkgdir/usr/lib/environment.d/99-charcoal-gaming.conf"
  # Charcoal: Install udev rules
  install -D -m 0644 -t "$pkgdir/etc/udev/rules.d" ../65-adios.rules
  install -D -m 0644 ../60-charcoal-zram-ir.rules \
    "$pkgdir/usr/lib/udev/rules.d/60-charcoal-zram-ir.rules"
  install -D -m 0755 ../configure-zram-ir \
    "$pkgdir/usr/lib/charcoal/configure-zram-ir"
  install -D -m 0644 ../90-charcoal-zram.conf \
    "$pkgdir/usr/lib/systemd/zram-generator.conf.d/90-charcoal-zram.conf"
  install -D -m 0644 ../90-charcoal-zram-ir.conf \
    "$pkgdir/usr/lib/systemd/system/systemd-zram-setup@.service.d/90-charcoal-zram-ir.conf"

  # Configure host swap after installation, never in the build environment.
  install -D -m 0755 ../configure-gaming-swap \
    "$pkgdir/usr/lib/gaming-swap/configure"
  install -D -m 0644 ../gaming-zswap.service \
    "$pkgdir/usr/lib/systemd/system/gaming-zswap.service"

  # Preserve NAP learning and build the offline viewer from this kernel's model.
  python3 "$srcdir/nap-tools-latest/install-tools.py" \
    --source-dir "$srcdir/nap-tools-latest" --require-resolved \
    --destdir "$pkgdir" --kernel-dir "$PWD/drivers/cpuidle/governors/nap"

  # Charcoal: Install bundles DKMS modules
  ZSTD_CLEVEL=19 _make_llvm M=../ryzen_smu INSTALL_MOD_PATH="$pkgdir/usr" INSTALL_MOD_STRIP=1 DEPMOD=/doesnt/exist modules_install
  ZSTD_CLEVEL=19 _make_llvm M=../xone INSTALL_MOD_PATH="$pkgdir/usr" INSTALL_MOD_STRIP=1 DEPMOD=/doesnt/exist modules_install
  ZSTD_CLEVEL=19 _make_llvm M=../xpad-noone INSTALL_MOD_PATH="$pkgdir/usr" INSTALL_MOD_STRIP=1 DEPMOD=/doesnt/exist modules_install
  ZSTD_CLEVEL=19 _make_llvm M=../xpadneo/hid-xpadneo/src INSTALL_MOD_PATH="$pkgdir/usr" INSTALL_MOD_STRIP=1 DEPMOD=/doesnt/exist modules_install
  cd ../xpadneo/hid-xpadneo
  install -D -m 0644 -t "$pkgdir/etc/modprobe.d" etc-modprobe.d/xpadneo.conf
  install -D -m 0644 -t "$pkgdir/etc/udev/rules.d" etc-udev-rules.d/60-xpadneo.rules
  install -D -m 0644 -t "$pkgdir/etc/udev/rules.d" etc-udev-rules.d/70-xpadneo-disable-hidraw.rules

  # remove build link
  rm "$modulesdir"/build
}

_package-headers() {
  pkgdesc="Headers and scripts for building modules for the $pkgdesc kernel"
  depends=(
    pahole
    llvm
    clang
    lld
    polly
  )

  cd $_srcname
  local builddir="$pkgdir/usr/lib/modules/$(<version)/build"

  echo "Installing build files..."
  install -Dt "$builddir" -m644 .config Makefile Module.symvers System.map \
    localversion.* version vmlinux tools/bpf/bpftool/vmlinux.h
  install -Dt "$builddir/kernel" -m644 kernel/Makefile
  install -Dt "$builddir/arch/x86" -m644 arch/x86/Makefile
  cp -t "$builddir" -a scripts
  ln -srt "$builddir" "$builddir/scripts/gdb/vmlinux-gdb.py"

  # required when STACK_VALIDATION is enabled
  install -Dt "$builddir/tools/objtool" tools/objtool/objtool

  # required when DEBUG_INFO_BTF_MODULES is enabled
  install -Dt "$builddir/tools/bpf/resolve_btfids" tools/bpf/resolve_btfids/resolve_btfids

  echo "Installing headers..."
  cp -t "$builddir" -a include
  cp -t "$builddir/arch/x86" -a arch/x86/include
  install -Dt "$builddir/arch/x86/kernel" -m644 arch/x86/kernel/asm-offsets.s

  install -Dt "$builddir/drivers/md" -m644 drivers/md/*.h
  install -Dt "$builddir/net/mac80211" -m644 net/mac80211/*.h

  # https://bugs.archlinux.org/task/13146
  install -Dt "$builddir/drivers/media/i2c" -m644 drivers/media/i2c/msp3400-driver.h

  # https://bugs.archlinux.org/task/20402
  install -Dt "$builddir/drivers/media/usb/dvb-usb" -m644 drivers/media/usb/dvb-usb/*.h
  install -Dt "$builddir/drivers/media/dvb-frontends" -m644 drivers/media/dvb-frontends/*.h
  install -Dt "$builddir/drivers/media/tuners" -m644 drivers/media/tuners/*.h

  # https://bugs.archlinux.org/task/71392
  install -Dt "$builddir/drivers/iio/common/hid-sensors" -m644 drivers/iio/common/hid-sensors/*.h

  echo "Installing KConfig files..."
  find . -name 'Kconfig*' -exec install -Dm644 {} "$builddir/{}" \;

  echo "Removing unneeded architectures..."
  local arch
  for arch in "$builddir"/arch/*/; do
    [[ $arch = */x86/ ]] && continue
    echo "Removing $(basename "$arch")"
    rm -r "$arch"
  done

  echo "Removing documentation..."
  rm -r "$builddir/Documentation"

  echo "Removing broken symlinks..."
  find -L "$builddir" -type l -printf 'Removing %P\n' -delete

  echo "Removing loose objects..."
  find "$builddir" -type f -name '*.o' -printf 'Removing %P\n' -delete

  echo "Stripping build tools..."
  local file
  while read -rd '' file; do
    case "$(file -Sib "$file")" in
      application/x-sharedlib\;*)      # Libraries (.so)
        strip -v $STRIP_SHARED "$file" ;;
      application/x-archive\;*)        # Libraries (.a)
        strip -v $STRIP_STATIC "$file" ;;
      application/x-executable\;*)     # Binaries
        strip -v $STRIP_BINARIES "$file" ;;
      application/x-pie-executable\;*) # Relocatable binaries
        strip -v $STRIP_SHARED "$file" ;;
    esac
  done < <(find "$builddir" -type f -perm -u+x ! -name vmlinux -print0)

  echo "Stripping vmlinux..."
  strip -v $STRIP_STATIC "$builddir/vmlinux"

  echo "Adding symlink..."
  mkdir -p "$pkgdir/usr/src"
  ln -sr "$builddir" "$pkgdir/usr/src/$pkgbase"
}

_package-docs() {
  pkgdesc="Documentation for the $pkgdesc kernel"

  cd $_srcname
  local builddir="$pkgdir/usr/lib/modules/$(<version)/build"

  echo "Installing documentation..."
  local src dst
  while read -rd '' src; do
    dst="${src#Documentation/}"
    dst="$builddir/Documentation/${dst#output/}"
    install -Dm644 "$src" "$dst"
  done < <(find Documentation -name '.*' -prune -o ! -type d -print0)

  echo "Adding symlink..."
  mkdir -p "$pkgdir/usr/share/doc"
  ln -sr "$builddir/Documentation" "$pkgdir/usr/share/doc/$pkgbase"
}

# Jupiter: Don't package the docs
#pkgname=(
#  "$pkgbase"
#  "$pkgbase-headers"
#  "$pkgbase-docs"
#)
pkgname=("$pkgbase" "$pkgbase-headers")
for _p in "${pkgname[@]}"; do
  eval "package_$_p() {
    $(declare -f "_package${_p#$pkgbase}")
    _package${_p#$pkgbase}
  }"
done

# vim:set ts=8 sts=2 sw=2 et:

