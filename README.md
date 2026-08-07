# Charcoal SteamOS Kernel — SteamOS 7.2 branch

This branch is the experimental Charcoal line for **SteamOS 7.2**. It is intentionally isolated from the stable `master`/6.16 line.

> **Important:** builds produced from `kernel-7.2` are experimental and are published only as **GitHub prereleases**. The stable Charcoal installer does not consume them.

## Source policy

The build resolves the newest official `linux-neptune-72` source package from Valve's SteamOS package index, maps it to the corresponding `linux-integration` 7.2 tag, and then resolves the maintained Charcoal patch stack for that source. The exact source package, Valve tag, patch origins, commits and SHA-256 values are recorded in the build logs and `patch-lock.json`.

## Install the SteamOS 7.2 prerelease

Run this from SteamOS Desktop Mode:

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/kernel-7.2/install-charcoal.sh -o install-charcoal-7.2.sh && bash install-charcoal-7.2.sh
```

The installer is pinned to this 7.2 release line. It searches GitHub Releases for the newest published prerelease whose tag starts with `charcoal-7.2-` and accepts only a `linux-charcoal-72-*.zip` bundle plus `RELEASE-ZIP-SHA256SUM`.

Before any package is changed, the installer:

- downloads the complete prerelease bundle;
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

Every successful kernel build triggered from `kernel-7.2` is packaged into a release ZIP, accompanied by SHA-256 metadata, and published as a GitHub **prerelease** with a `charcoal-7.2-...` tag. Re-running the same workflow run updates the same prerelease assets rather than creating a stable release.

The normal stable `releases/latest` endpoint is deliberately not used by the 7.2 installer because GitHub excludes prereleases from that stable-release path.

## Current 7.2 kernel configuration

The 7.2 branch keeps the Charcoal gaming/memory configuration, including the dedicated 7.2 zram-ir port. The expected ZRAM policy remains LZ4 primary compression with ZSTD priority-1 recompression fixed to the equivalent of `zstd --fast=1` in the kernel port.

## Build workflow

The dedicated workflow is:

`.github/workflows/build-kernel-7.2.yml`

It runs only for the `kernel-7.2` branch or a manual dispatch on that branch. A successful compile is followed by prerelease bundle creation and publication; publication failure makes the workflow fail rather than silently leaving a compiled kernel unpublished.

## Warning

SteamOS 7.2 support in this branch is experimental. Do not use the 7.2 installer on a device unless you intend to test this prerelease kernel line and understand how to recover the stock SteamOS kernel if needed.

For the stable Charcoal kernel, use the `master` branch instead.
