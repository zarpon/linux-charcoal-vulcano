#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "automation" / filename)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


resolver = module("adios_616_resolver", "resolve-latest-patches.py")
validator = module("adios_616_lock", "validate-patch-lock.py")
PATCH = b'''diff --git a/block/adios.c b/block/adios.c
new file mode 100644
--- /dev/null
+++ b/block/adios.c
@@ -0,0 +1,17 @@
+#define ADIOS_VERSION "3.3.0"
+/* unchanged r2 scheduler implementation sentinel */
+\tdata->shallow_depth = ad->async_depth;
+static void adios_depth_updated(struct request_queue *q) {
+\tstruct adios_data *ad = q->elevator->elevator_data;
+
+\tad->async_depth = q->async_depth;
+\tblk_mq_set_min_shallow_depth(q, ad->async_depth);
+}
+// Define sysfs attributes
+static struct elv_fs_entry adios_sched_attrs[] = {
+// Initialize the scheduler-specific data when initializing the request queue
+\tq->async_depth = q->nr_requests;
+\tadios_depth_updated(q);
+\t\t.init_sched\t\t\t= adios_init_sched,
+/* end scheduler sentinel */
diff --git a/block/Makefile b/block/Makefile
--- a/block/Makefile
+++ b/block/Makefile
@@ -39,3 +40,10 @@
 context
 context
 context
+
+all:
+\tmake -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules
+
+clean:
+\tmake -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean
+
diff --git a/block/elevator.c b/block/elevator.c
--- a/block/elevator.c
+++ b/block/elevator.c
@@ -1 +1 @@
-old integration
+new integration
diff --git a/scripts/setlocalversion b/scripts/setlocalversion
--- a/scripts/setlocalversion
+++ b/scripts/setlocalversion
@@ -117,7 +117,7 @@ scm_version()
 \t\t# If only the short version is requested, don't bother
 \t\t# running further git commands
 \t\tif $short; then
-\t\t\techo "+"
+\t\t\t#echo "+"
 \t\t\treturn
 \t\tfi
__BLANK_CONTEXT__
'''.replace(b"__BLANK_CONTEXT__", b" ")


class Adios616PortTests(unittest.TestCase):
    def test_r2_raw_depth_and_writable_control_are_preserved(self):
        port = resolver.port_adios_616(PATCH)
        self.assertIn(b"data->shallow_depth = ad->async_depth;", port)
        self.assertNotIn(b"to_word_depth", port)
        self.assertNotIn(b"q->async_depth", port)
        self.assertIn(b"AD_ATTR_RW(async_depth)", port)
        self.assertIn(b"kstrtouint(page, 10, &depth)", port)
        self.assertIn(b"if (!depth)", port)
        self.assertIn(b"WRITE_ONCE(ad->async_depth, depth)", port)
        self.assertIn(b"READ_ONCE(ad->async_depth)", port)
        depth_callback = port.split(b"+static void adios_depth_updated", 1)[1].split(b"+}", 1)[0]
        self.assertNotIn(b"ad->async_depth =", depth_callback)
        for sentinel in (b"unchanged r2 scheduler implementation sentinel", b"end scheduler sentinel"):
            self.assertIn(sentinel, port)

    def test_shared_hunk_asserts_lru_prerequisite_without_dropping_section(self):
        port = resolver.port_adios_616(PATCH)
        self.assertEqual(port.count(b"diff --git a/scripts/setlocalversion"), 1)
        self.assertIn(b'-\t\t\t#echo "+"\n+\t\t\t#echo "+"\n', port)
        self.assertNotIn(b'-\t\t\techo "+"', port)

    def test_unreviewed_revision_and_version_fail_closed(self):
        with self.assertRaises(resolver.ResolveError):
            resolver.port_adios_616(PATCH, "3.3.0r3")
        with self.assertRaises(resolver.ResolveError):
            resolver.port_adios_616(PATCH.replace(b'ADIOS_VERSION "3.3.0"', b'ADIOS_VERSION "3.4.0"'))

    def test_missing_or_ambiguous_control_fails_closed(self):
        anchor = b"+// Define sysfs attributes\n"
        for modified in (PATCH.replace(anchor, b""), PATCH.replace(anchor, anchor * 2)):
            with self.subTest(modified=modified):
                with self.assertRaises(resolver.ResolveError):
                    resolver.port_adios_616(modified)

    def test_changed_shared_hunk_fails_closed(self):
        with self.assertRaises(resolver.ResolveError):
            resolver.port_adios_616(PATCH.replace(b'+\t\t\t#echo "+"', b'+\t\t\t#different'))

    def test_resolver_keeps_raw_upstream_hash_separate_from_adapted_hash(self):
        record = {
            "origin": "adaptive-port", "adapter": "adios-valve-616",
            "project_version": "3.3.0r2", "content_bytes": PATCH,
        }
        with mock.patch.object(resolver, "_ORIGINAL_RESOLVE_GITHUB_COMPONENT", return_value=record):
            selected = resolver.resolve_github_component({}, "6.16.12", None, ROOT)
        self.assertEqual(selected["upstream_sha256"], hashlib.sha256(PATCH).hexdigest())
        self.assertEqual(selected["upstream_size"], len(PATCH))
        self.assertNotEqual(hashlib.sha256(selected["content_bytes"]).hexdigest(), selected["upstream_sha256"])

    def test_lock_rejects_missing_adapted_source_checksum(self):
        spec = {"kind": "github_tree", "target": "adios.patch", "adaptive_port": "adios-valve-616"}
        record = {
            "origin": "adaptive-port", "adapter": "adios-valve-616",
            "target": "adios.patch", "sha256": "a" * 64, "size": 1,
            "commit": "b" * 40, "path": "upstream.patch", "url": "https://example.invalid",
            "upstream_sha256": "c" * 64, "upstream_size": 10,
        }
        validator.validate_record("adios", spec, record)
        for key in ("upstream_sha256", "upstream_size"):
            modified = {k: v for k, v in record.items() if k != key}
            with self.assertRaises(validator.ValidationError):
                validator.validate_record("adios", spec, modified)


if __name__ == "__main__":
    unittest.main()
