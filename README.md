# Charcoal SteamOS Kernel — stable channel

[Português brasileiro](README.pt-BR.md)

`master` builds the Charcoal kernel for the current **SteamOS stable** channel. SteamOS 3.9 stable currently ships Linux 7.2; these are different version numbers. The complete maintained `kernel-7.2` stack has replaced the former 6.18 pipeline on `master`.

## Install Latest

Update SteamOS stable, then run in Desktop Mode. On Steam Deck, enable IOMMU in BIOS and reboot first.

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/master/install-charcoal.sh -o install-charcoal.sh && bash install-charcoal.sh
```

The installer reads GitHub's [releases/latest](https://github.com/zarpon/linux-charcoal-vulcano/releases/latest), rejecting drafts, prereleases and Preview tags. It accepts a versioned stable `charcoal-<kernel package version>-r<run>` tag, one `linux-charcoal-<series>-*.zip` bundle and `RELEASE-ZIP-SHA256SUM`. Package names follow the resolved kernel series: currently `linux-charcoal-72` and `linux-charcoal-72-headers`, with a corresponding suffix for future kernels.

Before package changes, the installer verifies the ZIP SHA-256, safely extracts exactly the matching kernel/headers pair, verifies both package hashes and queries package metadata with pacman. `pacman -Qp` checks metadata; it does not simulate the complete transaction or available space.

It identifies previous `linux-charcoal*` packages and the conflicting stock kernel/headers for the selected series. Stock removal requires explicit confirmation; unrelated packages are excluded. After transaction confirmation, it enables filesystem writes and developer mode, removes approved packages with narrowly scoped `pacman -Rdd`, installs the verified pair, reapplies the persistent swap configuration and updates GRUB. Read-only mode is restored on exit. It never reboots automatically.

Exact cached copies in `/var/cache/pacman/pkg` are staged for rollback. If the new installation fails and every removed package was cached, restoration is attempted. Without complete cache copies, automatic rollback cannot be guaranteed: repair a failed kernel installation before rebooting. Keep a SteamOS recovery method available.

Existing unattended options are preserved: `CHARCOAL_72_REMOVE_STOCK=1` explicitly authorizes stock removal and `CHARCOAL_72_ASSUME_YES=1` accepts both prompts. Their legacy names remain compatible across kernel series.

After success, reboot manually and check `uname -r` and `pacman -Q | grep '^linux-charcoal'`. The running kernel should contain the installed Charcoal series suffix. Use this installer with the current SteamOS stable release, not an older unsupported OS image.

## Automatic stable tracking

The source of truth is Valve's [stable update metadata](https://steamdeck-atomupd.steamos.cloud/meta/holo/steamos/amd64/steamdeck/stable.json), not the largest kernel number in a source index. `automation/prepare-steamos-stable.py`:

1. Selects an image explicitly marked `stable`, with its SteamOS version and build ID.
2. Downloads that exact image's `.manifest.pacman` from Valve's image server.
3. Identifies the exact installed `linux-neptune-<series>` package/version.
4. Derives the matching source repository from the SteamOS major/minor version: 3.9 uses `jupiter-3.9`; 3.10 automatically uses `jupiter-3.10`.
5. Requires that exact source archive, resolves its Valve tag, fetches its Arch/Valve config and updates package names and the patch compatibility target.

Thus, a stable transition to Linux 7.3 or newer is discovered automatically, even when the SteamOS repository changes. Preview/main images and RC/beta kernel packages are rejected. Missing or ambiguous stable metadata fails the build; there is no silent fallback to main or an older source. Exact image, package-manifest URL, source URL, tag and series are recorded in `steamos-stable-source.json`.

Kernel discovery does not bypass patch compatibility. Every patch family remains required. The newest upstream project version is selected first, preferring a native variant for the resolved series; tracked ports/adapters preserve their upstream hashes and lineage. Existing ports are checked against the new source before compilation. If upstream bytes or kernel APIs change incompatibly, the build fails for correction instead of removing a patch, downgrading its project version or publishing an incomplete kernel. See [PATCH-SOURCES.md](PATCH-SOURCES.md).

The maintained stack includes BORE/sched_ext coexistence, POC Selector, ADIOS/default elevator, LRU Marie, NAP, ZRAM-IR, AMD P-State EPP boost, CPU/O3 optimizations, Clear/Zen changes, DKMS/Clang/Polly compatibility, firmware/wireless adjustments, Ryzen SMU, controller drivers and local Van Gogh/IOMMU patches. Application order is preserved. `6.16.12-bore-6.8.0-final.patch` is retained as a compatibility reference; the current BORE source is selected dynamically. Superseded 6.18 payloads are replaced by their maintained 7.2 implementations.

Functionality already present in Valve's source remains accounted for by the resolver instead of being applied twice. Retired fsync opcode-31, C23/libbpf, Bluetooth SSP and upstream Qualcomm ath11k patches already absent from `kernel-7.2` are not reintroduced. The validated `patch-lock.json` records actual patch versions, origins, hashes and upstream-provided functionality.

## Build and release policy

[push.yml](.github/workflows/push.yml) builds and publishes on `master` pushes. Pull requests and `validation/**` builds do not publish. A manual dispatch supports `publish_release=false` for artifacts only. The daily build runs at **03:05 UTC / 00:05 Brasília**, dispatching only `master`.

Stable releases use `draft = false`, `prerelease = false`, `latest = true`. Both creation and update explicitly set Latest. Source/lock validation, checksum verification, patch preparation, config checks, compilation and packaging must succeed first. The workflow then rereads release flags/assets and `/releases/latest`; publication or readback failure fails the run. Historical releases are retained.

Assets include kernel and headers, the ZIP, checksums, patch lock and stable-source metadata. Release notes are generated from that build's validated lock. The ZIP also carries the patch lock, source metadata and checksum audit.

`kernel-7.2` is retained for manual development builds only. [build-kernel-7.2.yml](.github/workflows/build-kernel-7.2.yml) has no push/schedule trigger or release publication steps; it uploads artifacts. It is no longer dispatched by the daily workflow.

For local preparation with Python 3, Bash and Git:

```bash
python3 automation/prepare-pkgbuild-7.2.py --write PKGBUILD
python3 automation/prepare-steamos-stable.py --fetch-config
python3 automation/resolve-controller-drivers.py --write
python3 automation/resolve-latest-patches-7.2-policy.py --overrides logs/patch-source-overrides-stable.json --write
python3 automation/validate-patch-lock.py --manifest logs/patch-sources-7.2.json --overrides logs/patch-source-overrides-stable.json
```

Some helper filenames retain `7.2` for compatibility; the stable entry point supplies the dynamically detected series. The Dockerfile provides Arch Linux/LLVM. The workflow finalizes checksums from resolved bytes, verifies sources, prepares patches and compiles with makepkg. Static tests do not replace target-hardware boot testing.

## Preserved runtime features

The software Crypto API ZSTD default is **level 1** (ZSTD_DEF_LEVEL=1), used by generic ZSTD zswap. The existing code derives compression parameters and workspace sizes automatically; its window limit and decompressor are unchanged. The build checks the prepared source and publishes zstd-crypto-level.txt and zstd-crypto-source.sha256. This default also applies to other users of the generic Crypto API codec. ZRAM-IR's separate fast setting and hardware-specific Intel QAT backends retain their existing behavior.


O3 and Charcoal gaming/memory configuration remain enabled. Installation persistently disables ZRAM/services, enables ZSTD zswap with a **35% RAM pool**, shrinker enabled, and a `/home` swapfile sized to **75% of RAM**. ZRAM-IR support remains available in the kernel. See [SWAP.md](SWAP.md).

Runtime values remain `vm.vfs_cache_pressure=100`, `vm.dirty_background_ratio=2` and `vm.dirty_ratio=5`, preserving LRU Marie defaults. `CONFIG_ZEN_INTERACTIVE` controls the existing evdev asynchronous RCU and P-State schedutil-selection changes, without importing additional Zen memory/scheduler defaults.

IOMMU PerfOpt automatically uses an optimized identity DMA path on eligible AMD integrated GPUs. While active, ATS, PRI, PASID and SVA/GCR3 setup is skipped for that device, reducing DMA containment. Results depend on hardware/workload, with no guaranteed percentage gain or `amdgpu.iommu_perfopt` runtime opt-out.

Every build fetches the latest NAP tools and records their commit/hashes. Learning persists across boots, with saves every 30 minutes. Includes `napctl` and `/usr/share/nap/napviz.html`, generated from the compiled kernel model. See [NAP-TOOLS.md](NAP-TOOLS.md).
