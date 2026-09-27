# Patch provenance

Baseline reviewed on Ubuntu source `linux 7.2.0-5.5`, Microsoft Surface Laptop 7 15-inch X1E / Romulus15 (SMBIOS SKU `Surface_Laptop_7th_Edition_2037`). Records before 2026-09-25 called this machine the 13.8-inch Romulus13 because it had booted the Romulus13 DTB; the hardware and all test results are unchanged. Subsequent Ubuntu versions require successful patch application, builds, and separate hardware qualification.

- `0001`: Local port of the ath12k rfkill workaround, limited to Romulus15, based on [bryce-hoehn/linux-surface-laptop-7](https://github.com/bryce-hoehn/linux-surface-laptop-7).
- `0002`: QSPI/GPI and SPI HID transport from [ProgrammerIn-wonderland/ELLX-Kernel](https://github.com/ProgrammerIn-wonderland/ELLX-Kernel), commit `0e9944fa4cf2ccf575f5162bfd53ed4dc1592251`, ported to Ubuntu with lifecycle fixes and Romulus15-only wiring. It targets Ubuntu `7.3.0-5.5` / upstream `v7.3-rc3`, retaining the upstream GENI resource callbacks, scoped runtime-PM acquisition and SA8255P support; see [the upstream audit](docs/7.3-upstream-audit.zh-CN.md). The original Ubuntu 7.2 version, which differed only in the SPI-controller portion, was retired on 2026-09-27 together with 7.2 support.
- `0003`: GTCH SPI touchscreen wiring derived from this model's Windows ACPI and the SPI transport investigation. It replaces the unsuccessful I2C touchscreen experiment; it is not the LKML I2C proposal.
- `0004`, `0005`: Local 2026-09-15 SPI HID power-lifecycle, GPIO ownership and DRM panel follower changes. These extend the first three patches and must be applied as a set.
- `0007`–`0012` (2026-09-27): Local SPI HID transport fixes on top of `0002`/`0004`, derived from static analysis of this machine's Windows `hidspi.sys` / `HidSpiCx.sys` (Microsoft public symbols) and `qcspi8380.sys`: bounded input reports and fragment reassembly, device-initiated reset recovery with a runtime `reset_recovery` switch, feature responses read under the lock, 4-byte output padding, power cycling of unresponsive devices, and supply error propagation. They touch only `drivers/hid/spi-hid/` and are not yet hardware-validated; see [the validation checklist](docs/spi-hid-windows-parity.zh-CN.md). No Windows code or disassembly is included.
- `0013`–`0017` (2026-09-27): Follow-ups to `0007`–`0012` from the same Windows analysis and the decoded `BSRC_QSPI*.bin` resources: removal of enumeration work left unused by `0008` (moving the HIDSPI version check into enumeration), report IDs passed only when the device sends one, re-reading while an edge-triggered interrupt stays asserted (with `irq-gpios` on the touchscreen), a probe-time log of `GENI_IF_DISABLE_RO` on QSPI controllers, and Windows' QSPI pin pull-downs and touchscreen drive strength. Checked against Ubuntu 7.3 only; not yet hardware-validated; see [the validation checklist](docs/spi-hid-windows-parity.zh-CN.md).
- `0006` (retired 2026-09-27; Ubuntu `7.3.0-6.6` / v7.3-rc4 carries the upstream fix [net: qrtr: resend HELLO on MHI resume](https://ratatoskr.run/lkml/2026/07/17348346/t)): Local revert of upstream [544d85de4dc2](https://github.com/torvalds/linux/commit/544d85de4dc22c01badfd8cefa59829ce35c4858), restoring QRTR HELLO handling after firmware restarts with a retained MHI endpoint. One deep-resume hardware test passed on Ubuntu `7.3.0-5.5` with the original PCIe policy. The reviewed optional series recognizes unaffected source without modifying it; unknown changes fail. See [the regression and validation record](docs/7.3-wifi-resume.zh-CN.md).

The original three-patch maintenance archive is [ItsLucas/surface-laptop-7-linux-maintenance](https://github.com/ItsLucas/surface-laptop-7-linux-maintenance). Existing patch headers and authorship are retained; no contributor sign-offs are fabricated. Kernel and device-tree changes retain the licenses of their respective upstream files. New CI scripts and tests are provided under GPL-2.0-only.

Ubuntu source, buildinfo versions and download URLs, the exact recipe commit, all patch hashes, public-certificate fingerprint, toolchain inventory and source package checksums are included in each `BUILD.json`. Reproduce using the repository at that commit and the recorded Ubuntu packages. No proprietary firmware is distributed by this pipeline.

## PLD hwmon modules

The original GPL-2.0-only implementation in `drivers/qcom-pld-power/` was developed
from locally observed Windows EMI metadata, static interface analysis of the
installed Qualcomm PEP driver, and Linux read-only/affinity/suspend experiments.
It is built as two external modules against each candidate kernel's generated
ABI; it is not a copied Windows driver or an upstream-merged kernel patch.

The protocol/resource evidence, driver hash, units, test scope and unresolved
questions are recorded in [`PROTOCOL.md`](drivers/qcom-pld-power/PROTOCOL.md) and
[`pld-power-validation.md`](docs/pld-power-validation.md). No proprietary binaries,
disassembly, raw device captures, private keys or firmware images are distributed.
