# Charcoal SteamOS Kernel — SteamOS 7.2 Preview

This branch is the experimental Charcoal line for **SteamOS 7.2**. It is intentionally isolated from the stable `master`/6.16 line and from the other kernel branches.

> **Important:** builds produced from `kernel-7.2` use their own **Charcoal 7.2 Preview** GitHub release channel. These releases are published releases, but they are explicitly **not** marked as GitHub prereleases and **not** marked as `Latest`, so they do not take ownership of the repository's normal latest/stable release channel.

## Source policy

The build resolves the newest official `linux-neptune-72` source package from Valve's SteamOS package index, maps it to the corresponding `linux-integration` 7.2 tag, and then resolves the maintained Charcoal patch stack for that source.

For every maintained patch family, the resolver selects the newest upstream project release first. It then prefers a native SteamOS 7.2/kernel 7.2 variant when one exists. If the newest upstream release has no usable 7.2 variant, the build must use a reviewed and tracked 7.2 port of that newest release instead of silently falling back to an older patch release merely because it applies without conflicts.

The exact Valve source package, Valve tag, patch origins, upstream commits, selected project versions and SHA-256 values are recorded in the build logs and `patch-lock.json`. Tracked ports are tied to the exact upstream bytes they implement so an upstream update forces a new review/port instead of silently reusing stale code.

## Install Charcoal 7.2 Preview

Run this from SteamOS Desktop Mode:

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/kernel-7.2/install-charcoal.sh -o install-charcoal-7.2.sh && bash install-charcoal-7.2.sh
```

The installer is pinned exclusively to the 7.2 Preview line. It scans GitHub Releases for the newest published release whose tag starts with `charcoal-7.2-preview-`, rejects drafts and GitHub prereleases, and accepts only a `linux-charcoal-72-*.zip` bundle plus `RELEASE-ZIP-SHA256SUM`.

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
- `prerelease = false`;
- `latest = false`.

A successful 7.2 build therefore remains a normal downloadable GitHub release while being isolated from the `Latest` release selected for other branches.

The installer selects this channel by its exclusive tag prefix and never relies on the repository-wide latest-release endpoint.

## Current 7.2 kernel configuration

The 7.2 branch keeps the Charcoal gaming/memory configuration, including the dedicated 7.2 zram-ir port. The expected ZRAM policy remains LZ4 primary compression with ZSTD priority-1 recompression fixed to the equivalent of `zstd --fast=1` in the kernel port.

## Build workflow

The dedicated workflow is:

`.github/workflows/build-kernel-7.2.yml`

It runs only for the `kernel-7.2` branch or a manual dispatch on that branch. Source resolution, patch-version policy validation, patch preflight and kernel compilation must all succeed before the **Charcoal 7.2 Preview** release is created or updated. Publication failure makes the workflow fail rather than silently leaving a compiled kernel unpublished.

## Warning

SteamOS 7.2 support in this branch is experimental. Do not use the 7.2 installer on a device unless you intend to test this Preview kernel line and understand how to recover the stock SteamOS kernel if needed.

For the stable Charcoal kernel, use the `master` branch instead.
