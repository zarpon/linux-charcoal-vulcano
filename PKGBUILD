# Maintainer: Thomas Rohloff <v10lator@myway.de>
# Maintainer: John Schoenick <johns@valvesoftware.com>
# Maintainer: Jan Alexander Steffens (heftig) <heftig@archlinux.org>

pkgbase=linux-charcoal-616
_nepbase=linux-neptune-616
_tag=6.16.12-valve27
_ver=1
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
_xpadneo_version=0.10.2
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
  latest-c23-libbpf.patch
  latest-clear.patch
  latest-fsync-futex-waitv.patch
  latest-o3.patch
  latest-bt-ssp-key-size.patch
  latest-libbpf-uninitialized.patch
  latest-cpu-optimizations.patch
  latest-dkms-clang.patch
  latest-clang-polly.patch
  latest-firmware-name.patch
  latest-minstrel-frac.patch
  latest-minstrel-fluctuation.patch
  latest-minstrel-downgrade.patch
  latest-ath11k-remapped-ce.patch
  latest-ath11k-disable-key.patch
  latest-ath11k-upstream.patch
  latest-adios.patch
  latest-adios-default.patch
  latest-bore.patch
  latest-bore-sched-ext-coexistence-fix.patch
  latest-zen-01.patch
  latest-zen-02.patch
  latest-zen-03.patch
  latest-zen-04.patch
  latest-zen-05.patch
  latest-zen-06.patch
  latest-zen-07.patch
  "git+https://github.com/amkillam/ryzen_smu.git#commit=9f9569f889935f7c7294cc32c1467e5a4081701a"
  "git+https://github.com/dlundqvist/xone.git#tag=v0.5.8"
  "git+https://github.com/forkymcforkface/xpad-noone.git#commit=8e903676dd9514c07ce5e06e43c5f7d8cc51cb7d"
  "git+https://github.com/atar-axis/xpadneo.git#tag=v$_xpadneo_version"
   latest-poc-selector.patch
  latest-nap.patch
)
sha256sums=(
  'SKIP'
  '37452b4d09e5e42134ae24a61f2f656790837c327268074cf79d7dab3558b972'
  'd88eaf0f94bae470040e4882f334c05b1bb2ab0a99e4b7299aa0b2337810ab8d'
  'e1e94e879c9b3f26b8e4a157c79b5cddc3f4d9dd08672307d49bd88ea0fc8acb'
  'b831de1b98a2f77f636f4780e37ebfcb3a6829f94f5423eb04c4b26e64ac43b8'
  'dc8d23ada60ea089c4f21514f72a22962747fd5fbf625d135236e8c82e4a5a6c'
  'f74713691121b2826220c519a6ceb088a11b757f6ddccfe61535490cee244a3c'
  '6e71f4ef06f4e40053ac530d0000669bcf65db6e3992ccee54f0c61f8ba04ec6'
  '52cbbf41450806d766260bc4f1ea055f6f9fdd55d37ad831840b16d505beb0cc'
  '35fc7647671b1ab412804143a0585dde8d9880097c06feb520f90680780ac5e5'
  '3e200a7ad9661f59be2dfd442fd993fd130da8a6f5df7d8b4ec40d86351b1dcd'
  'a2e63ecf61f7f91da8473658da4bde646c30915d443d7edec243862437f945a1'
  '07068c432fd7e80689f44a28346f1909de9ee77aa3e72dfaa6a4ea89d9921afd'
  '1f7df01db0bcd7c18230878003466ac3f651f8f21e74323b7e8178871d824f74'
  '375c8e17daf9e60bc6c211dd73f0c67ec241bd40a83d812a08eeb42aab6128d9'
  '1c49146dc5878bfab32b331d11cb66d493670bbe590ff07c2050305911c281c3'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  '4bcf61814a6daac8f72c46a425b9ce88c07f6bd95f6a0ac287d73dfd4d5da60b'
  'ff3bbe78d6f072d57f567878e870956242ee78ccddd258b1ec2e4729621138fe'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
  'SKIP'
)
export KBUILD_BUILD_HOST=archlinux
export KBUILD_BUILD_USER=$pkgbase
export KBUILD_BUILD_TIMESTAMP="$(date -Ru${SOURCE_DATE_EPOCH:+d @$SOURCE_DATE_EPOCH})"

prepare() {
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
    elif [[ $src == latest-c23-libbpf.patch ]]; then
      if patch --dry-run --batch -Np1 < "../$src" >/dev/null 2>&1; then
        patch --batch -Np1 < "../$src"
      elif patch --dry-run --batch -R -Np1 < "../$src" >/dev/null 2>&1; then
        echo "Skipping patch $src: already present in Valve base $_tag."
      else
        echo "ERROR: patch $src neither applies nor is already present in Valve base $_tag." >&2
        patch --dry-run --batch -Np1 < "../$src" || true
        return 1
      fi
    elif [[ $src == latest-libbpf-uninitialized.patch ]]; then
      patch -Np1 < "../$src"
      python3 "$startdir/automation/fix-libbpf-clang-warning.py" \
        tools/lib/bpf/elf.c
    else
      patch -Np1 < "../$src"
    fi
  done

  echo "Setting config..."
  cp ../config .config
  scripts/kconfig/merge_config.sh -m ../config ../config-neptune ../config-charcoal # Charcoal: merge the extra fragment
  _make_llvm olddefconfig
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
  pkgdesc="The $pkgdesc kernel and modules"
  depends=(
    coreutils
    initramfs
    kmod
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
