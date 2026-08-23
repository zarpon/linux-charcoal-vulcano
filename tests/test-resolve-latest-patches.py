#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "automation/resolve-latest-patches.py"
SPEC = importlib.util.spec_from_file_location("charcoal_patch_resolver", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

PATCH = b"From 1111111111111111111111111111111111111111 Mon Sep 17 00:00:00 2001\nSubject: [PATCH] demo\n\ndiff --git a/demo.c b/demo.c\n--- a/demo.c\n+++ b/demo.c\n@@ -1 +1 @@\n-old\n+new\n"
MBOX = (
    b"From nobody Tue Jul 28 07:31:55 2026\n"
    b"From: Example <example@example.invalid>\n"
    b"Subject: [PATCH] demo\n"
    b"MIME-Version: 1.0\n"
    b"Content-Type: text/plain; charset=UTF-8\n"
    b"Content-Transfer-Encoding: quoted-printable\n"
    b"\n"
    b"Demo patch body.\n"
    b"\n"
    b"---\n"
    b" demo.c | 2 +-\n"
    b" 1 file changed, 1 insertion(+), 1 deletion(-)\n"
    b"\n"
    b"diff --git a/demo.c b/demo.c\n"
    b"index 1111111..2222222 100644\n"
    b"--- a/demo.c\n"
    b"+++ b/demo.c\n"
    b"@@ -1 +1 @@\n"
    b"-old=3Dvalue\n"
    b"+new=3Dvalue\n"
    b"\n"
    b"-- \n"
    b"2.53.0\n"
)
DECODED_MBOX_PATCH = (
    b"---\n"
    b" demo.c | 2 +-\n"
    b" 1 file changed, 1 insertion(+), 1 deletion(-)\n"
    b"\n"
    b"diff --git a/demo.c b/demo.c\n"
    b"index 1111111..2222222 100644\n"
    b"--- a/demo.c\n"
    b"+++ b/demo.c\n"
    b"@@ -1 +1 @@\n"
    b"-old=value\n"
    b"+new=value\n"
)


class LocalPortTrackingTests(unittest.TestCase):
    def candidate(
        self,
        version: str | None,
        *,
        kernel: tuple[int, ...] = (6, 16, 0),
        compatibility: int = 0,
    ) -> object:
        return MODULE.Candidate(
            path="patches/stable/0001-linux6.18-demo-2.0.patch",
            sha="a" * 40,
            url="https://example.invalid/demo.patch",
            compatibility=compatibility,
            kernel_version=kernel,
            project_version=version,
        )

    @staticmethod
    def base_spec() -> dict[str, object]:
        upstream_sha = hashlib.sha256(PATCH).hexdigest()
        return {
            "name": "demo",
            "repository": "example/demo",
            "local_port": "demo.patch",
            "port_for_kernel": "6.18.45",
            "port_when_incompatible": True,
            "local_port_project_version": "1.0",
            "local_port_upstream_sha256": upstream_sha,
        }

    def test_version_change_rejects_stale_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate("2.0")]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                with self.assertRaisesRegex(MODULE.ResolveError, "selected closest upstream source is 2.0"):
                    MODULE.resolve_github_component(self.base_spec(), "6.18.45", None, root)

    def test_matching_version_accepts_tracked_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            spec = self.base_spec()
            spec["local_port_project_version"] = "2.0"
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate("2.0")]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                selected = MODULE.resolve_github_component(spec, "6.18.45", None, root)
        self.assertEqual(selected["origin"], "local-port")
        self.assertEqual(selected["upstream"]["project_version"], "2.0")

    def test_latest_native_series_patch_wins_over_a_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = self.base_spec()
            with mock.patch.object(
                MODULE,
                "upstream_candidates",
                return_value=[
                    self.candidate("2.0"),
                    self.candidate(
                        "2.0", kernel=(6, 18, 22), compatibility=2
                    ),
                ],
            ):
                selected = MODULE.resolve_github_component(
                    spec, "6.18.45", None, root
                )

        self.assertEqual(selected["origin"], "upstream-native")
        self.assertEqual(selected["selection"], "latest-native-series")
        self.assertEqual(selected["kernel_version"], "6.18.22")
        self.assertEqual(
            selected["fallback"],
            {
                "kind": "local-port",
                "path": "demo.patch",
                "kernel_version": "6.18.45",
                "project_version": "1.0",
                "upstream_sha256": hashlib.sha256(PATCH).hexdigest(),
            },
        )

    def test_lru_marie_testing_0106_prefers_the_native_618_variant(self) -> None:
        candidates = [
            MODULE.Candidate(
                "patches/testing/0001-linux6.16.12-lru_marie-0.10.6.patch",
                "a" * 40,
                "https://example.invalid/lru-6.16.patch",
                0,
                (6, 16, 12),
                "0.10.6",
            ),
            MODULE.Candidate(
                "patches/testing/0001-linux6.18.22-lru_marie-0.10.6.patch",
                "b" * 40,
                "https://example.invalid/lru-6.18.patch",
                2,
                (6, 18, 22),
                "0.10.6",
            ),
            MODULE.Candidate(
                "patches/testing/0001-linux7.1-rc5-lru_marie-0.10.6.patch",
                "c" * 40,
                "https://example.invalid/lru-7.1.patch",
                0,
                (7, 1),
                "0.10.6",
            ),
        ]
        spec = {"name": "lru_marie", "repository": "firelzrd/lru_marie"}
        with mock.patch.object(MODULE, "upstream_candidates", return_value=candidates):
            selected = MODULE.resolve_github_component(spec, "6.18.45", None, ROOT)

        self.assertEqual(selected["selection"], "latest-native-series")
        self.assertEqual(
            selected["path"],
            "patches/testing/0001-linux6.18.22-lru_marie-0.10.6.patch",
        )

    def test_unversioned_port_requires_upstream_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            spec = self.base_spec()
            spec.pop("local_port_project_version")
            spec.pop("local_port_upstream_sha256")
            with mock.patch.object(
                MODULE,
                "upstream_candidates",
                return_value=[self.candidate(None)],
            ), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                with self.assertRaisesRegex(MODULE.ResolveError, "must declare local_port_upstream_sha256"):
                    MODULE.resolve_github_component(spec, "6.18.45", None, root)


class MailboxLocalPortTests(unittest.TestCase):
    @staticmethod
    def spec(upstream_sha: str) -> dict[str, object]:
        return {
            "name": "mailbox_demo",
            "kind": "http_patch",
            "repository": "lore.kernel.org/linux-pm",
            "path": "demo@example.invalid",
            "commit": "demo@example.invalid",
            "target": "latest-mailbox-demo.patch",
            "urls": ["https://example.invalid/demo.mbox"],
            "mailbox": True,
            "local_port": "demo.port.patch",
            "port_for_kernel": "6.18.45",
            "local_port_upstream_sha256": upstream_sha,
        }

    def test_mailbox_is_decoded_before_hashing_and_upstream_is_selected_first(self) -> None:
        self.assertEqual(MODULE.decode_mailbox_patch(MBOX), DECODED_MBOX_PATCH)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.port.patch").write_bytes(PATCH)
            with mock.patch.object(MODULE, "request_bytes", return_value=MBOX):
                selected = MODULE.resolve_http_component(
                    self.spec(hashlib.sha256(DECODED_MBOX_PATCH).hexdigest()),
                    "6.18.45",
                    None,
                    root,
                )

        self.assertEqual(selected["origin"], "upstream-fixed")
        self.assertEqual(selected["selection"], "first-valid")
        self.assertEqual(selected["content_bytes"], DECODED_MBOX_PATCH)
        self.assertEqual(
            selected["fallback"],
            {
                "kind": "local-port",
                "path": "demo.port.patch",
                "kernel_version": "6.18.45",
                "upstream_sha256": hashlib.sha256(DECODED_MBOX_PATCH).hexdigest(),
            },
        )

    def test_changed_mailbox_payload_rejects_stale_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.port.patch").write_bytes(PATCH)
            with mock.patch.object(MODULE, "request_bytes", return_value=MBOX):
                with self.assertRaisesRegex(MODULE.ResolveError, "refresh and validate"):
                    MODULE.resolve_http_component(
                        self.spec("0" * 64), "6.18.45", None, root
                    )


class OfficialKernelSourceTests(unittest.TestCase):
    @staticmethod
    def config() -> dict[str, object]:
        return {
            "repository": "example/linux-integration",
            "series": "6.18",
            "tag_regex": r"^(?P<version>6\.18\.\d+)-valve(?P<valve>[0-9.]+)$",
            "official_source_index": "https://packages.example.invalid/sources/",
            "official_package_regex": (
                r"^linux-neptune-618-(?P<version>6\.18\.\d+)"
                r"\.valve(?P<valve>[0-9.]+)-(?P<pkgrel>\d+)\.src\.tar\.gz$"
            ),
        }

    def test_official_source_index_limits_the_selected_mirror_tag(self) -> None:
        listing = b'''<a href="linux-neptune-618-6.18.44.valve9-1.src.tar.gz">old</a>
<a href="linux-neptune-618-6.18.45.valve1-1.src.tar.gz">current</a>
<a href="linux-neptune-618-6.18.45.valve1-2.src.tar.gz">current rebuild</a>'''
        refs = [
            {
                "ref": "refs/tags/6.18.45-valve1",
                "object": {"sha": "a" * 40, "type": "commit"},
            },
            {
                "ref": "refs/tags/6.18.46-valve1",
                "object": {"sha": "b" * 40, "type": "commit"},
            },
        ]
        with (
            mock.patch.object(MODULE, "request_bytes", return_value=listing),
            mock.patch.object(MODULE, "request_json", return_value=refs),
        ):
            tag, commit, package = MODULE.resolve_kernel_tag(self.config(), None)

        self.assertEqual(tag, "6.18.45-valve1")
        self.assertEqual(commit, "a" * 40)
        self.assertEqual(package["filename"], "linux-neptune-618-6.18.45.valve1-2.src.tar.gz")
        self.assertEqual(package["pkgrel"], 2)

    def test_missing_official_mirror_tag_is_rejected(self) -> None:
        listing = b'<a href="linux-neptune-618-6.18.45.valve1-1.src.tar.gz">current</a>'
        refs = [
            {
                "ref": "refs/tags/6.18.44-valve9",
                "object": {"sha": "a" * 40, "type": "commit"},
            }
        ]
        with (
            mock.patch.object(MODULE, "request_bytes", return_value=listing),
            mock.patch.object(MODULE, "request_json", return_value=refs),
        ):
            with self.assertRaisesRegex(MODULE.ResolveError, "requires mirror tag"):
                MODULE.resolve_kernel_tag(self.config(), None)


if __name__ == "__main__":
    unittest.main()
