#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "automation/prepare-pkgbuild-7.2.py"
SPEC = importlib.util.spec_from_file_location("prepare_pkgbuild_72", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ZEN_PATH = ROOT / "automation/port-zen-cpufreq-7.2.py"
ZEN_SPEC = importlib.util.spec_from_file_location("port_zen_cpufreq_72", ZEN_PATH)
assert ZEN_SPEC and ZEN_SPEC.loader
ZEN = importlib.util.module_from_spec(ZEN_SPEC)
sys.modules[ZEN_SPEC.name] = ZEN
ZEN_SPEC.loader.exec_module(ZEN)

SWAP_PATH = ROOT / "automation/port-zen-swap-7.2.py"
SWAP_SPEC = importlib.util.spec_from_file_location("port_zen_swap_72", SWAP_PATH)
assert SWAP_SPEC and SWAP_SPEC.loader
SWAP = importlib.util.module_from_spec(SWAP_SPEC)
sys.modules[SWAP_SPEC.name] = SWAP
SWAP_SPEC.loader.exec_module(SWAP)

SAMPLE = '''pkgbase=linux-charcoal-616
_nepbase=linux-neptune-616
_tag=6.16.12-valve27
source=(
  config
  latest-c23-libbpf.patch
  latest-ath11k-upstream.patch
  latest-adios.patch
  latest-adios-default.patch
  latest-bore.patch
  latest-bore-sched-ext-coexistence-fix.patch
  latest-zen-01.patch
  latest-zen-02.patch
  latest-zen-07.patch
  latest-poc-selector.patch
)
prepare() {
  if [[ $src == latest-poc-selector.patch ]]; then :; fi
}
'''

ZEN_PATCH = '''From test
diff --git a/drivers/cpufreq/Kconfig.x86 b/drivers/cpufreq/Kconfig.x86
@@ -9,7 +9,6 @@ config X86_INTEL_PSTATE
-	select CPU_FREQ_GOV_SCHEDUTIL if SMP
@@ -39,7 +38,6 @@ config X86_AMD_PSTATE
-	select CPU_FREQ_GOV_SCHEDUTIL if SMP
'''

VALVE_72_KCONFIG = '''config X86_INTEL_PSTATE
	bool "Intel P state control"
	select CPU_FREQ_GOV_PERFORMANCE
	select CPU_FREQ_GOV_SCHEDUTIL if SMP
	help

config X86_AMD_PSTATE
	bool "AMD Processor P-State driver"
	depends on ACPI
	select ACPI_PROCESSOR
	select ACPI_CPPC_LIB if X86_64
	select CPU_FREQ_GOV_SCHEDUTIL if SMP
	select ACPI_PLATFORM_PROFILE
	select POWER_SUPPLY
	help

config X86_ACPI_CPUFREQ
	tristate "ACPI Processor P-States driver"
'''

REMOVED_LINE = "-\tselect CPU_FREQ_GOV_SCHEDUTIL if SMP\n"

ZEN_SWAP_PATCH = '''From test
diff --git a/init/Kconfig b/init/Kconfig
@@ -184,6 +184,7 @@ config ZEN_INTERACTIVE
+	    Swap-in readahead..............:   3    ->   0
diff --git a/mm/swap.c b/mm/swap.c
@@ -1091,6 +1091,10 @@ void __init swap_setup(void)
+#ifdef CONFIG_ZEN_INTERACTIVE
+	page_cluster = 0;
'''

VALVE_72_SWAP = '''void __init swap_setup(void)
{
	unsigned long megs = PAGES_TO_MB(totalram_pages());

	if (megs < 16)
		page_cluster = 2;
	else
		page_cluster = 3;

	register_sysctl_init("vm", swap_sysctl_table);
}
'''


class TransformTests(unittest.TestCase):
    def test_transforms_identifiers_and_patch_order(self) -> None:
        result = MODULE.transform(SAMPLE)
        MODULE.validate(result)
        self.assertIn("pkgbase=linux-charcoal-72", result)
        positions = [result.index(name) for name in MODULE.PATCH_ORDER]
        self.assertEqual(positions, sorted(positions))

    def test_skips_patches_already_upstream_in_valve_72(self) -> None:
        result = MODULE.transform(SAMPLE)
        for patch in ("latest-c23-libbpf.patch", "latest-ath11k-upstream.patch"):
            self.assertIn(patch, result)
            self.assertIn(patch, MODULE.UPSTREAMED_72_PATCHES)
        self.assertIn(
            "Skipping $src: Valve 7.2 already contains the upstream change.",
            result,
        )
        self.assertIn("continue", result)

    def test_wires_explicit_zen_cpufreq_port(self) -> None:
        result = MODULE.transform(SAMPLE)
        self.assertEqual(result.count("latest-zen-02.patch"), 2)
        self.assertEqual(result.count("port-zen-cpufreq-7.2.py"), 1)

    def test_zen_cpufreq_adapter_handles_valve_72_layout(self) -> None:
        ZEN.validate_patch(ZEN_PATCH)
        adapted = ZEN.adapt_source(VALVE_72_KCONFIG)
        self.assertNotIn(ZEN.TARGET, adapted)
        self.assertIn("\tselect ACPI_PLATFORM_PROFILE\n", adapted)
        self.assertIn("\tselect POWER_SUPPLY\n", adapted)

    def test_zen_cpufreq_adapter_rejects_patch_shape_drift(self) -> None:
        with self.assertRaisesRegex(ZEN.PortError, "exactly two"):
            ZEN.validate_patch(ZEN_PATCH.replace(REMOVED_LINE, "", 1))

    def test_wires_explicit_zen_swap_port(self) -> None:
        result = MODULE.transform(SAMPLE)
        self.assertEqual(result.count("latest-zen-07.patch"), 2)
        self.assertEqual(result.count("port-zen-swap-7.2.py"), 1)

    def test_zen_swap_adapter_preserves_valve_72_body(self) -> None:
        SWAP.validate_patch(ZEN_SWAP_PATCH)
        adapted = SWAP.adapt_source(VALVE_72_SWAP)
        self.assertIn("#ifdef CONFIG_ZEN_INTERACTIVE", adapted)
        self.assertIn("\tpage_cluster = 0;\n", adapted)
        self.assertIn("PAGES_TO_MB(totalram_pages())", adapted)
        self.assertIn("#else\n", adapted)

    def test_is_idempotent(self) -> None:
        once = MODULE.transform(SAMPLE)
        twice = MODULE.transform(once)
        self.assertEqual(once, twice)

    def test_missing_patch_is_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.TransformError, "missing patch"):
            MODULE.transform(SAMPLE.replace("  latest-adios.patch\n", ""))


if __name__ == "__main__":
    unittest.main()
