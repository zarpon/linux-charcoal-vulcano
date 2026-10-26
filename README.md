# Charcoal — manual Linux 7.2 development branch

The maintained stable line is now [`master`](https://github.com/zarpon/linux-charcoal-vulcano/tree/master). SteamOS 3.9 stable uses Linux 7.2; the version numbers refer to different projects.

This branch no longer publishes GitHub releases or prereleases and has no automatic push/daily build. The `Build SteamOS 7.2 development kernel manually` workflow can be dispatched on `kernel-7.2` to produce downloadable Actions artifacts only. Historical Preview releases remain available, but no new ones are published. Artifact filenames may retain the historical Preview naming.

## Stable installation

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/master/install-charcoal.sh -o install-charcoal.sh && bash install-charcoal.sh
```

The bundled installer also follows `releases/latest`, accepting stable releases with `prerelease = false`. It rejects historical Preview tags, verifies the ZIP and kernel/headers SHA-256, requires confirmation before replacing conflicting packages, preserves rollback from exact cached archives when available, restores read-only mode and never reboots automatically. On Steam Deck, enable IOMMU in BIOS first.

The master pipeline automatically discovers the current SteamOS stable image, its exact kernel and the matching source repository, including future SteamOS 3.10 / Linux 7.3 transitions. See the [stable README](https://github.com/zarpon/linux-charcoal-vulcano/blob/master/README.md) for source policy, installation details and recovery limits. Local preparation commands in that document apply to `master`; this retained branch uses its dedicated manual 7.2 workflow.

## Preserved development payload

No kernel patches or runtime features were removed from this branch. It retains BORE/sched_ext coexistence, POC Selector, ADIOS, LRU Marie, NAP, ZRAM-IR, AMD P-State, CPU optimizations, LLVM/Polly compatibility, controller drivers, Ryzen SMU, Van Gogh and IOMMU patches, together with their existing source-selection policy.

O3, ZSTD zswap (35% RAM pool, shrinker enabled), persistent ZRAM disabling and a `/home` swapfile sized to 75% RAM remain. Runtime values remain `vm.vfs_cache_pressure=100`, `vm.dirty_background_ratio=2`, `vm.dirty_ratio=5`; LRU Marie defaults are preserved. NAP tools and learning persistence are retained. See [SWAP.md](SWAP.md) and [NAP-TOOLS.md](NAP-TOOLS.md).

IOMMU PerfOpt retains its existing identity DMA path on eligible AMD integrated GPUs, with the same ATS/PRI/PASID/SVA tradeoffs. No performance percentage is guaranteed.
