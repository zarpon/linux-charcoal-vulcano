# CAST migration validation — 2026-10-26

Every build discovers the newest complete upstream release (including RC/rN),
then selects its native kernel variant or ports that release from the nearest
available series. Older native releases do not win over a newer foreign release.

Live resolution selected `firelzrd/lru_cast` commit
`71c94c9fd7270c8c260ef7a861cb043bfb375321`, CAST `0.2.5`,
`patches/0001-7.2-rc1-lru_cast-v0.2.5.patch` for Valve 7.2.7.
These are validation results, not fixed build versions.

The complete upstream patch passed `git apply --check` against all 25 existing
source files it modifies from `evlaV/linux-integration@7.2.7-valve2`; new files
come from the patch. No adaptation was needed. Upstream SHA-256:
`c8e9d88c68307dec60bc7baf6064c003358bd55df6fd2ea31d5d9867f49cd85a`.

The combined targeted suite across both repositories passed 85 tests, covering
selection, revisions, audits, lock validation, patch application, default
configuration and integration. Python compilation, shell syntax and refreshed
hashes for config-charcoal/99-charcoal-sysctl.conf also passed. The shell-backed
configuration gate ran under bundled Git Bash with POSIX mode disabled.

`CONFIG_LRU_CAST=y` is enforced after olddefconfig. CAST is enabled by default
upstream. No swappiness assignment remains in the packaged sysctl configuration.
The previous Marie port is removed. Locked upstream bytes are kept separately
from any derived patch, and an unrecognized API change fails before application.

Full kernel compilation and boot validation have not been performed locally.
Broad Windows test discovery also has Linux tooling/symlink limitations; only
the targeted passing suite is claimed here. Unknown future API changes require
a reviewed port, never a silent fallback to an older upstream release.
