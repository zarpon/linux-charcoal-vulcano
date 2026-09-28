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
TAG_PREFIX = "charcoal-7.2-preview-"
ZIP_PREFIX = "linux-charcoal-72-"


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

    def test_selects_published_preview_prerelease_over_newer_stable(self) -> None:
        result = self.run_selector(
            [
                release("charcoal-7.2-preview-7.2.2-r124", prerelease=False),
                release("charcoal-7.2-preview-7.2.1-r123", prerelease=True),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], "charcoal-7.2-preview-7.2.1-r123")

    def test_skips_draft_and_wrong_series_prereleases(self) -> None:
        result = self.run_selector(
            [
                release("charcoal-7.2-preview-7.2.2-r124", prerelease=True, draft=True),
                release("charcoal-6.18.50-r125", prerelease=True),
                release("charcoal-7.2-preview-7.2.1-r123", prerelease=True),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], "charcoal-7.2-preview-7.2.1-r123")

    def test_refuses_a_channel_with_only_stable_releases(self) -> None:
        result = self.run_selector(
            [release("charcoal-7.2-preview-7.2.2-r124", prerelease=False)]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prerelease", result.stderr)

    def test_refuses_ambiguous_archives(self) -> None:
        result = self.run_selector(
            [release("charcoal-7.2-preview-7.2.1-r123", prerelease=True, zip_count=2)]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete or ambiguous", result.stderr)

    def test_workflow_creates_and_updates_only_non_latest_prereleases(self) -> None:
        workflow = (ROOT / ".github/workflows/build-kernel-7.2.yml").read_text(
            encoding="utf-8"
        )
        publish = workflow.split("      - name: Publish Charcoal 7.2 Preview release", 1)[1]
        publish = publish.split("      - name: Verify Preview release flags", 1)[0]
        self.assertEqual(publish.count("--prerelease"), 2, publish)
        self.assertEqual(publish.count("--latest=false"), 2, publish)
        verify = workflow.split("      - name: Verify Preview release flags", 1)[1]
        self.assertIn("assert record['isPrerelease'] is True", verify)
        self.assertIn("assert record['isLatest'] is False", verify)

    def test_readmes_describe_the_prerelease_installer_contract(self) -> None:
        for name in ("README.md", "README.pt-BR.md"):
            readme = (ROOT / name).read_text(encoding="utf-8").lower()
            self.assertIn("prerelease = true", readme)
            self.assertIn("charcoal-7.2-preview-", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
