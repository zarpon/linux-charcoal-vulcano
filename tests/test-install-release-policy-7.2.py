#!/usr/bin/env python3
"""Exercise the exact release-selection Python embedded in install-charcoal.sh."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install-charcoal.sh"
REPOSITORY = "zarpon/linux-charcoal-vulcano"
DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
TAG_PREFIX = "charcoal-"
ZIP_PREFIX = "linux-charcoal-"


def embedded_selector() -> str:
    source = INSTALLER.read_text(encoding="utf-8")
    function = re.search(
        r"^parse_release_metadata\(\) \{(?P<body>.*?)^\}\s*\n\s*verify_release_archive\(",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if function is None:
        raise AssertionError("installer release-selection function was not found")
    script = re.search(r"<<'PY'\n(?P<script>.*?)\nPY\s*$", function.group("body"), re.DOTALL)
    if script is None:
        raise AssertionError("installer's embedded release selector was not found")
    return script.group("script") + "\n"


def release(tag: str, *, prerelease: bool, draft: bool = False, zip_count: int = 1):
    assets = []
    for index in range(zip_count):
        name = f"{ZIP_PREFIX}7.2.1-r123{'-' + str(index) if index else ''}.zip"
        assets.append(
            {
                "name": name,
                "browser_download_url": f"{DOWNLOAD_PREFIX}{tag}/{name}",
            }
        )
    assets.append(
        {
            "name": "RELEASE-ZIP-SHA256SUM",
            "browser_download_url": f"{DOWNLOAD_PREFIX}{tag}/RELEASE-ZIP-SHA256SUM",
        }
    )
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets,
    }


class InstallerReleasePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.selector = embedded_selector()
        compile(cls.selector, "installer-release-selector", "exec")

    def run_selector(self, releases: list[dict[str, object]]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            release_file = Path(directory) / "releases.json"
            release_file.write_text(json.dumps(releases), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    "-",
                    str(release_file),
                    REPOSITORY,
                    DOWNLOAD_PREFIX,
                    TAG_PREFIX,
                    ZIP_PREFIX,
                ],
                input=self.selector,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_selects_latest_stable_72(self):
        result = self.run_selector(release("charcoal-7.2.7.valve2.cc1-r1", prerelease=False))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], "charcoal-7.2.7.valve2.cc1-r1")

    def test_refuses_preview_drafts_old_series_and_list_responses(self):
        cases = [
            release("charcoal-7.2-preview-7.2.7-r1", prerelease=True),
            release("charcoal-7.2.7-r1", prerelease=True),
            release("charcoal-7.2.7-r1", prerelease=False, draft=True),
            release("charcoal-7.2-preview-7.2.7-r1", prerelease=False),
            release("charcoal-6.18.53.valve1.cc1-r1", prerelease=False),
            [release("charcoal-7.2.7-r1", prerelease=False)],
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertNotEqual(self.run_selector(case).returncode, 0)

    def test_refuses_ambiguous_archives(self):
        result = self.run_selector(release("charcoal-7.2.7.valve2.cc1-r1", prerelease=False, zip_count=2))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete or ambiguous", result.stderr)

    def test_refuses_asset_from_another_repository(self):
        record = release("charcoal-7.2.7.valve2.cc1-r1", prerelease=False)
        record["assets"][0]["browser_download_url"] = "https://github.com/other/repo/releases/download/tag/kernel.zip"
        result = self.run_selector(record)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing asset outside", result.stderr)

    def test_development_workflow_is_manual_and_never_publishes(self):
        manual = (ROOT / ".github/workflows/build-kernel-7.2.yml").read_text()
        triggers = manual.split("on:", 1)[1].split("permissions:", 1)[0]
        self.assertEqual(triggers.strip(), "workflow_dispatch:")
        self.assertNotIn("gh release create", manual)
        self.assertNotIn("gh release edit", manual)

    def test_readmes_describe_stable_latest_installer(self):
        for name in ("README.md", "README.pt-BR.md"):
            readme = (ROOT / name).read_text().lower()
            self.assertIn("prerelease = false", readme)
            self.assertIn("releases/latest", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
