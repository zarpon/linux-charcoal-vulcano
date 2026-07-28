#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github/workflows/push.yml"
text = PATH.read_text(encoding="utf-8")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


text = replace_once(
    text,
    "'automation/patch-sources.json', 'automation/resolve-latest-patches.py'",
    "'automation/patch-sources.json', 'automation/patch-source-overrides.json', 'automation/resolve-latest-patches.py'",
    "cache input policy",
)
text = replace_once(
    text,
    "          python3 automation/validate-patch-lock.py | tee logs/patch-lock-validation.log",
    "          python3 automation/validate-patch-lock.py | tee logs/patch-lock-validation.log\n          python3 tests/test-bore-overlay.py",
    "overlay policy test",
)
text = replace_once(
    text,
    "            makepkg --verifysource 2>&1 | tee logs/verifysource-bootstrap.log",
    "            makepkg --verifysource --skipchecksums 2>&1 | tee logs/verifysource-bootstrap.log",
    "bootstrap source fetch",
)
old = '''          bore = lock["components"]["bore"]
          assert bore["origin"] == "local-port"
          assert bore["selection"] == "latest-upstream-port"
          assert bore["upstream"]["path"] == "patches/testing/0001-linux6.18.22-bore-6.8.0-rc1.patch"
          assert bore["upstream"]["sha256"] == "356f9b2935e3ca79c3bcfa87d8630b6fec3fb731049c81cc7086fbbaa58f5e60"
'''
new = '''          bore = lock["components"]["bore"]
          assert bore["origin"] == "local-port"
          assert bore["selection"] == "latest-upstream-port"
          with open("automation/patch-source-overrides.json", encoding="utf-8") as handle:
              bore_policy = json.load(handle)["components"]["bore"]
          upstream = bore["upstream"]
          expected_version = bore_policy["local_port_project_version"]
          assert upstream["project_version"] == expected_version
          assert upstream["path"].endswith(f"-bore-{expected_version}.patch")
          assert re.fullmatch(r"[0-9a-f]{40}", upstream["commit"])
          assert re.fullmatch(r"[0-9a-f]{64}", upstream["sha256"])
          assert [item["path"] for item in bore["local_port_overlays"]] == bore_policy["local_port_overlays"]
'''
text = replace_once(text, old, new, "dynamic BORE lock assertions")
PATH.write_text(text, encoding="utf-8")
