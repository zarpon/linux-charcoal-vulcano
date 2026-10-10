# Charcoal SteamOS Kernel — SteamOS 7.2 Preview

This branch is the experimental Charcoal line for **SteamOS 7.2**. It is intentionally isolated from the stable `master`/6.18 line and from the other kernel branches.

> **Important:** builds produced from `kernel-7.2` use their own **Charcoal 7.2 Preview** GitHub release channel. Every successful build on this branch is published as a GitHub **prerelease**, never as `Latest`, so it does not take ownership of the repository's stable release channel.

## Source policy

The build resolves the newest official `linux-neptune-72` source package from Valve's SteamOS package index, maps it to the corresponding `linux-integration` 7.2 tag, and then resolves the maintained Charcoal patch stack for that source.

For every maintained patch family, the resolver selects the newest upstream project release first. It then prefers a native SteamOS 7.2/kernel 7.2 variant when one exists. If the newest upstream release has no usable 7.2 variant, the build must use a reviewed and tracked 7.2 port of that newest release instead of silently falling back to an older patch release merely because it applies without conflicts.

The exact Valve source package, Valve tag, patch origins, upstream commits, selected project versions and SHA-256 values are recorded in the build logs and `patch-lock.json`. Tracked ports are tied to the exact upstream bytes they implement so an upstream update forces a new review/port instead of silently reusing stale code.

## Install Charcoal 7.2 Preview

Run this from SteamOS Desktop Mode:
> **Steam Deck BIOS requirement:** Before installing on a Steam Deck, make sure
> IOMMU is enabled in BIOS. Save the setting and reboot.

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/kernel-7.2/install-charcoal.sh -o install-charcoal-7.2.sh && bash install-charcoal-7.2.sh
```

The installer is pinned exclusively to the 7.2 Preview line. It scans GitHub Releases for the newest published **prerelease** whose tag starts with `charcoal-7.2-preview-`, rejects drafts and ordinary releases, and accepts only a `linux-charcoal-72-*.zip` bundle plus `RELEASE-ZIP-SHA256SUM`.

It does **not** use `releases/latest`, so installing the 7.2 Preview kernel never depends on which release another branch currently owns as the repository's Latest release.

Before any package is changed, the installer:

- downloads the complete 7.2 Preview bundle;
- verifies the release ZIP SHA-256;
- verifies the SHA-256 of both the `linux-charcoal-72` kernel and headers packages inside the ZIP;
- asks pacman to preflight the verified packages;
- detects installed packages whose names begin with `linux-charcoal`;
- shows the transaction and requires confirmation before making SteamOS writable.

After validation and confirmation, any previous Charcoal kernel packages are removed with a narrowly scoped `pacman -Rdd` transaction before the verified SteamOS 7.2 kernel and headers are installed. Packages such as `linux-neptune-*` and unrelated packages are never part of that removal list. `-Rdd` is used specifically to avoid cascading dependency removal.

If exact previous Charcoal package archives are still available in `/var/cache/pacman/pkg`, the installer copies them to its temporary workspace before removal and attempts to restore them automatically if installation of the new 7.2 packages fails. If no rollback copy is available and installation fails after removal, the installer stops, warns not to reboot, and restores the SteamOS root filesystem to read-only mode.

The installer never reboots automatically. After a successful installation, reboot manually and verify:

```bash
uname -r
```

The result should contain `charcoal-72`.

## Release policy for this branch

Every successful kernel build triggered from `kernel-7.2` is packaged into a dedicated release ZIP with SHA-256 metadata and published with:

- release title: **Charcoal 7.2 Preview**;
- exclusive tag prefix: `charcoal-7.2-preview-`;
- `prerelease = true`;
- `latest = false`.

A successful 7.2 build therefore appears in GitHub's prerelease channel while remaining isolated from the `Latest` stable release selected for other branches.

The installer requires both the exclusive tag prefix and GitHub's prerelease flag; it never relies on the repository-wide latest-release endpoint.

## Current 7.2 kernel configuration

The 7.2 branch keeps the Charcoal gaming/memory configuration, including the dedicated 7.2 zram-ir port. ZRAM-IR remains available, but installation disables zram and uses LZ4 zswap backed by a swapfile on the home filesystem.

### AMD IOMMU PerfOpt

On supported AMD IOMMUs, PerfOpt is enabled automatically for eligible integrated
GPUs using an identity DMA domain. The optimized IOMMU path may reduce DMA
latency. ATS, PRI, PASID, and SVA/GCR3 setup is skipped for that device
while PerfOpt is active, reducing IOMMU DMA containment on this path. The actual
effect depends on hardware and workload; no percentage gain is guaranteed. There
is no amdgpu.iommu_perfopt runtime opt-out.

## Build workflow

The dedicated workflow is:

`.github/workflows/build-kernel-7.2.yml`

It runs only for the `kernel-7.2` branch or a manual dispatch on that branch. Source resolution, patch-version policy validation, patch preflight and kernel compilation must all succeed before the **Charcoal 7.2 Preview** release is created or updated. Publication failure makes the workflow fail rather than silently leaving a compiled kernel unpublished.

## Warning

SteamOS 7.2 support in this branch is experimental. Do not use the 7.2 installer on a device unless you intend to test this Preview kernel line and understand how to recover the stock SteamOS kernel if needed.

For the stable Charcoal kernel, use the `master` branch instead.

## Compilation and swap profile

The kernel uses O3. Installation enables LZ4 zswap with a 50% RAM pool,
shrinker enabled and a 150% RAM swapfile on the `/home` filesystem. ZRAM
and its setup services are disabled persistently. See [SWAP.md](SWAP.md)
for migration details and verification.

Runtime tuning uses `vm.vfs_cache_pressure=100`,
`vm.dirty_background_ratio=2` and `vm.dirty_ratio=10`. LRU Marie's own defaults
are preserved.

`CONFIG_ZEN_INTERACTIVE` controls only the two existing Zen patches: evdev
asynchronous RCU reclamation and removal of forced P-State schedutil selects.
No additional Zen memory or scheduler defaults are imported.
The legacy fsync opcode-31 patch and already-upstream C23/libbpf, Bluetooth
SSP and Qualcomm ath11k patches are not fetched or applied.
