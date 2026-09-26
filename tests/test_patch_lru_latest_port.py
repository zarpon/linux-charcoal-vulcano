#!/usr/bin/env python3
"""Exact implementation hashes audited from upstream a05089b, newest r2."""
import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_FILES = {
    "include/linux/lru_marie.h": "6ae3fa0d5147df2b3b459831003e48fca0570902b0ca5663613fcba1d9fe4bb1",
    "mm/lru_marie/Makefile": "a26de139dd515617da628cc4ff09c60911f74e69aedab5a8abee4852f5fea97c",
    "mm/lru_marie/account.h": "77c76d8a8accbcb98afaa29da999f43ec4b18f3bc7b8fc73c5a8f630ccc34303",
    "mm/lru_marie/bitmap.c": "992fd11af052a0ea027d03c50f2b2c460aadaa7ae7367cf257179745882434ad",
    "mm/lru_marie/bitmap.h": "504cc23ebec44e1aa9df26afbd14e68eeec3d336069588e9304ad28c4100fb45",
    "mm/lru_marie/core.c": "d9cc15997389db33ef55b352ae0172f2ef4a0e83d78065bdf21c19455c793033",
    "mm/lru_marie/defrag.c": "90129f09e2d06597d056dbbe52b3d84df4bf4647ccdb465433123483a7ab7333",
    "mm/lru_marie/defrag.h": "fc66e1e56d54231abcacbb29609f5aa6cb1391bf68146913ffae372102fc286b",
    "mm/lru_marie/defrag_compat.h": "951feae1c71bd4a6d95a0acf191bc93aace17187648ca52f86e2849407c6b82b",
    "mm/lru_marie/pfn_install.h": "6d76e099fd4871c1ec296ca66783e5a8826f5a94fe29cad95c36adf710d57e8d",
    "mm/lru_marie/prefetch.h": "61df9b7f2e4e9de73e2746797f1243bcb381b5abc683cd6a37dd88b28f512575",
    "mm/lru_marie/simd.h": "8a6167651c3a252e96d239e080bb24677195a6f134cbb870721122a7de519389",
    "mm/lru_marie/simd_generic.c": "f7fc219f2e4180a6334a059e6a5e8ea65e73f4326e8623146da3e9f9a0b37f52",
    "mm/lru_marie/simd_x86.c": "f1bd8165f89dfe9c30d7863c2a7264fea534cb95630716a8c32577c494a26fb6",
    "mm/lru_marie/simd_x86_avx2.S": "adb65e620846342937b3a17f3a7b60e783e05a4ab28ff5e60f14b85d1bbe0717",
    "mm/lru_marie/simd_x86_avx512.S": "0d178d8b1fa1aeea40ced67525be3c8477457a09d246209bf6b83fd89d27122e",
    "mm/lru_marie/simd_x86_sse2.S": "7ba6bb471146d3048e64277a31dca5379c808fc6cdc3b41b31d9fe666d00d461",
    "mm/lru_marie/state.h": "163ff46756bda5a83c00ecfe314abceab7c713941f4ea03536149a308a4c918f",
    "mm/lru_marie/state_compat.h": "9148fe50565c43cba169db93ee8062ad1dbe6f33c91459bfe999f42adff1f598",
    "mm/lru_marie/state_core.c": "f7b8eb2508b261b87eff152e0edde4ad1fbff521d9e0631cbc5e24f101becde4",
    "mm/lru_marie/state_folio.c": "faaf0cb4fc6bc0a9f996dd867dd1e5963e966bd6ac6a5d83d08557b68f5efb9f",
    "mm/lru_marie/state_reclaim.c": "4f84df380c2ac842bb3d5e570aa6394b3b3f1d4f50261ec426ea9198033e2bbf",
    "mm/lru_marie/version.h": "2743feafa63a37884ba7dbc0a568094be269842bc805490e969a15442b93fef1",
    "mm/lru_marie/walker.c": "5683f0075b7ef06af729117d45c13be26132cc98cd4dc01e8d04a5bf46a5d458",
    "mm/lru_marie/walker_compat.h": "c0ba8aee05b0d95b99971241580a97451bf50ef465c65e0969508e45b2cc7afb"
}


class LruLatestPortTests(unittest.TestCase):
    def project_files(self):
        patch = (ROOT / "6.16.12-lru-marie-0.11.1r2.port.patch").read_text(encoding="utf-8")
        found = {}
        for block in re.split(r"(?m)(?=^diff --git )", patch):
            if not block.startswith("diff --git ") or "new file mode" not in block:
                continue
            path = block.splitlines()[0].split(" b/", 1)[1]
            if "lru_marie" not in path:
                continue
            body = re.split(r"(?m)^@@[^\n]*\n", block, maxsplit=1)[1]
            lines = []
            for line in body.splitlines():
                if line.startswith("+"):
                    lines.append(line[1:])
                elif line.startswith("-- "):
                    break
            self.assertNotIn(path, found)
            found[path] = "\n".join(lines) + "\n"
        return found

    def test_all_25_project_files_match_newest_upstream_except_target_api_glue(self):
        found = self.project_files()
        # Only this target API adaptation is permitted; normalize it back to
        # the authenticated r2 payload before checking all 25 upstream hashes.
        path = "mm/lru_marie/state_compat.h"
        for target, upstream in (
            ("Valve 6.16 already has shrink_folio_list()'s trailing @memcg (the scan is",
             "shrink_folio_list() gained a trailing @memcg parameter in 6.18 (the scan is"),
            ("does not forward it on the pre-6.16 signature.",
             "does not forward it on the pre-6.18 signature."),
            ("{\n#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 16, 0)\n\treturn shrink_folio_list",
             "{\n#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 18, 0)\n\treturn shrink_folio_list"),
        ):
            self.assertEqual(found[path].count(target), 1)
            found[path] = found[path].replace(target, upstream)
        found = {path: hashlib.sha256(body.encode()).hexdigest()
                 for path, body in found.items()}
        self.assertEqual(found, UPSTREAM_FILES)

    def test_valve_616_reclaim_wrapper_forwards_native_memcg_argument(self):
        # Signature from Valve 6.16.12-valve28 at 9f266e6d1b267bafcc016d2a05c04f573c6275b3,
        # mm/vmscan.c; it already has the sixth argument before any patches.
        native = ("struct list_head *folio_list, struct pglist_data *pgdat, "
                  "struct scan_control *sc, struct reclaim_stat *stat, "
                  "bool ignore_references, struct mem_cgroup *memcg")
        patch = (ROOT / "6.16.12-lru-marie-0.11.1r2.port.patch").read_text(encoding="utf-8")
        declaration = re.search(r"\+unsigned int shrink_folio_list\((.*?)\);", patch, re.S)
        self.assertIsNotNone(declaration)
        self.assertEqual(" ".join(declaration[1].replace("\n+", " ").split()), native)
        header = self.project_files()["mm/lru_marie/state_compat.h"]
        wrapper = header.split("marie_shrink_folio_list(", 1)[1].split("\n}", 1)[0]
        gate = re.search(r"#if LINUX_VERSION_CODE >= KERNEL_VERSION\((\d+), (\d+), (\d+)\)", wrapper)
        self.assertIsNotNone(gate)
        branches = wrapper.split(gate[0], 1)[1].split("#else", 1)
        native_arity = len(native.split(","))
        for version in ((6, 16, 12), (6, 18, 50), (7, 3, 0)):
            selected = branches[0] if version >= tuple(map(int, gate.groups())) else branches[1]
            call = re.search(r"return shrink_folio_list\((.*?)\);", selected, re.S)[1]
            self.assertEqual(len(call.split(",")), native_arity)
            self.assertEqual(call.split(",")[-1].strip(), "memcg")
        # Reproduce the old gate's deterministic failure on the exact target.
        old_call = re.search(r"return shrink_folio_list\((.*?)\);", branches[1], re.S)[1]
        self.assertEqual(len(old_call.split(",")), native_arity - 1)


if __name__ == "__main__":
    unittest.main()
