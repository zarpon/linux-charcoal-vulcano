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
    def candidate(self, version: str | None) -> object:
        return MODULE.Candidate(
            path="patches/stable/0001-linux6.16-demo-2.0.patch",
            sha="a" * 40,
            url="https://example.invalid/demo.patch",
            compatibility=2,
            kernel_version=(6, 16, 0),
            project_version=version,
        )

    @staticmethod
    def base_spec() -> dict[str, object]:
        return {
            "name": "demo",
            "repository": "example/demo",
            "local_port": "demo.patch",
            "port_for_kernel": "6.16.12",
            "port_when_incompatible": True,
            "local_port_project_version": "1.0",
        }

    def test_version_change_rejects_stale_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate("2.0")]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                with self.assertRaisesRegex(MODULE.ResolveError, "selected closest upstream source is 2.0"):
                    MODULE.resolve_github_component(self.base_spec(), "6.16.12", None, root)

    def test_matching_version_accepts_tracked_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            spec = self.base_spec()
            spec["local_port_project_version"] = "2.0"
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate("2.0")]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                selected = MODULE.resolve_github_component(spec, "6.16.12", None, root)
            self.assertEqual(selected["origin"], "local-port")
            self.assertEqual(selected["upstream"]["project_version"], "2.0")

    def test_unversioned_port_requires_upstream_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.patch").write_bytes(PATCH)
            spec = self.base_spec()
            spec.pop("local_port_project_version")
            with mock.patch.object(MODULE, "upstream_candidates", return_value=[self.candidate(None)]), mock.patch.object(MODULE, "request_bytes", return_value=PATCH):
                with self.assertRaisesRegex(MODULE.ResolveError, "must declare local_port_upstream_sha256"):
                    MODULE.resolve_github_component(spec, "6.16.12", None, root)


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
            "local_port_upstream_sha256": upstream_sha,
        }

    def test_mailbox_is_decoded_before_hashing_and_local_port_selection(self) -> None:
        self.assertEqual(MODULE.decode_mailbox_patch(MBOX), DECODED_MBOX_PATCH)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.port.patch").write_bytes(PATCH)
            with mock.patch.object(MODULE, "request_bytes", return_value=MBOX):
                selected = MODULE.resolve_http_component(
                    self.spec(hashlib.sha256(DECODED_MBOX_PATCH).hexdigest()),
                    "6.16.12",
                    None,
                    root,
                )

        self.assertEqual(selected["origin"], "local-port")
        self.assertEqual(selected["content_bytes"], PATCH)
        self.assertEqual(
            selected["upstream"]["sha256"],
            hashlib.sha256(DECODED_MBOX_PATCH).hexdigest(),
        )

    def test_changed_mailbox_payload_rejects_stale_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.port.patch").write_bytes(PATCH)
            with mock.patch.object(MODULE, "request_bytes", return_value=MBOX):
                with self.assertRaisesRegex(MODULE.ResolveError, "refresh and validate"):
                    MODULE.resolve_http_component(
                        self.spec("0" * 64), "6.16.12", None, root
                    )


if __name__ == "__main__":
    unittest.main()
