#!/usr/bin/env python3
"""Exercise GUD TV-mode input boundaries and fail-closed source adaptation."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "automation/fix-gud-tv-mode-fortify.py"
SPEC = importlib.util.spec_from_file_location("fix_gud_fortify", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# The reviewed upstream function, before adaptation.
ORIGINAL = r'''
static int gud_connector_add_tv_mode(struct gud_device *gdrm, struct drm_connector *connector)
{
	size_t buf_len = GUD_CONNECTOR_TV_MODE_MAX_NUM * GUD_CONNECTOR_TV_MODE_NAME_LEN;
	const char *modes[GUD_CONNECTOR_TV_MODE_MAX_NUM];
	unsigned int i, num_modes;
	char *buf;
	int ret;

	buf = kmalloc(buf_len, GFP_KERNEL);
	if (!buf)
		return -ENOMEM;

	ret = gud_usb_get(gdrm, GUD_REQ_GET_CONNECTOR_TV_MODE_VALUES,
			  connector->index, buf, buf_len);
	if (ret < 0)
		goto free;
	if (!ret || ret % GUD_CONNECTOR_TV_MODE_NAME_LEN) {
		ret = -EIO;
		goto free;
	}

	num_modes = ret / GUD_CONNECTOR_TV_MODE_NAME_LEN;
	for (i = 0; i < num_modes; i++) {
		char *mode = &buf[i * GUD_CONNECTOR_TV_MODE_NAME_LEN];

		if (!memchr(mode, '\0', GUD_CONNECTOR_TV_MODE_NAME_LEN)) {
			ret = -EIO;
			goto free;
		}

		modes[i] = mode;
	}

	ret = drm_mode_create_tv_properties_legacy(connector->dev, num_modes, modes);
free:
	kfree(buf);
	if (ret < 0)
		gud_conn_err(connector, "Failed to add TV modes", ret);

	return ret;
}
'''

C_PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#define GUD_CONNECTOR_TV_MODE_NAME_LEN 16
#define GUD_CONNECTOR_TV_MODE_MAX_NUM 16
#define GUD_REQ_GET_CONNECTOR_TV_MODE_VALUES 1
#define GFP_KERNEL 0
struct gud_device { int unused; };
struct drm_connector { unsigned int index; void *dev; };
static int response, terminated = 1, allocation_fails, calls;
static unsigned int observed;
#define kmalloc(n, flags) (allocation_fails ? NULL : malloc(n))
#define kmalloc_array(n, size, flags) kmalloc((n) * (size), flags)
#define kfree(p) free(p)
#define gud_conn_err(...) ((void)0)
static int gud_usb_get(struct gud_device *d, int req, unsigned int index,
                       void *buf, size_t len)
{
    memset(buf, terminated ? 0 : 'x', len);
    return response;
}
static int drm_mode_create_tv_properties_legacy(void *dev, unsigned int n,
                                                const char *const *modes)
{
    calls++;
    observed = n;
    for (unsigned int i = 0; i < n; i++)
        assert(strlen(modes[i]) < GUD_CONNECTOR_TV_MODE_NAME_LEN);
    return 0;
}
'''

C_MAIN = r'''
static void check(int bytes, int expected, unsigned int modes)
{
    struct gud_device device = {0};
    struct drm_connector connector = {0};
    calls = 0;
    response = bytes;
    assert(gud_connector_add_tv_mode(&device, &connector) == expected);
    assert(calls == (expected == 0));
    if (!expected)
        assert(observed == modes);
}
int main(void)
{
    check(-EPIPE, -EPIPE, 0);
    check(0, -EIO, 0);
    check(15, -EIO, 0);
    check(16, 0, 1);
    check(256, 0, 16);
    /* Aligned oversized responses must be rejected before scanning slots. */
    check(272, -EIO, 0);
    check(257, -EIO, 0);
    terminated = 0;
    check(16, -EIO, 0);
    allocation_fails = 1;
    check(16, -ENOMEM, 0);
    return 0;
}
'''


class GudFortifyTests(unittest.TestCase):
    def test_usb_response_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "gud.c"
            binary = Path(directory) / "gud-test"
            source.write_text(C_PREFIX + MODULE.adapt(ORIGINAL) + C_MAIN)
            subprocess.run(
                ["cc", "-O3", "-D_FORTIFY_SOURCE=3", "-Werror",
                 str(source), "-o", str(binary)], check=True,
            )
            subprocess.run([str(binary)], check=True)

    def test_adaptation_is_local_and_idempotent(self) -> None:
        before = "static char *buf;\n"
        after = "static int unrelated;\n"
        result = MODULE.adapt(before + ORIGINAL + after)
        self.assertTrue(result.startswith(before))
        self.assertTrue(result.endswith(after))
        self.assertEqual(MODULE.adapt(result), result)

    def test_source_drift_does_not_partially_write(self) -> None:
        changed = ORIGINAL.replace("ret / GUD_CONNECTOR_TV_MODE_NAME_LEN", "ret / 8")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "gud_connector.c"
            source.write_text(changed)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source anchor changed", result.stderr)
            self.assertEqual(source.read_text(), changed)


if __name__ == "__main__":
    unittest.main()
