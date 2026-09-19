# Patch provenance

Baseline reviewed on Ubuntu source `linux 7.2.0-5.5`, Microsoft Surface Laptop 7 13.8-inch X1E / Romulus13. Subsequent Ubuntu versions require successful patch application, builds, and separate hardware qualification.

- `0001`: Local port of the Romulus13 ath12k rfkill workaround, based on [bryce-hoehn/linux-surface-laptop-7](https://github.com/bryce-hoehn/linux-surface-laptop-7).
- `0002`: QSPI/GPI and SPI HID transport from [ProgrammerIn-wonderland/ELLX-Kernel](https://github.com/ProgrammerIn-wonderland/ELLX-Kernel), commit `0e9944fa4cf2ccf575f5162bfd53ed4dc1592251`, ported to Ubuntu with lifecycle fixes and Romulus13-only wiring.
- `variants/7.3/0002`: Same hardware support rebased to Ubuntu `7.3.0-5.5` / upstream `v7.3-rc3`, retaining the upstream GENI resource callbacks, scoped runtime-PM acquisition and SA8255P support. This variant replaces only the SPI-controller portion; the other portions match the original 0002. See [the upstream audit](docs/7.3-upstream-audit.zh-CN.md).
- `0003`: GTCH SPI touchscreen wiring derived from this model's Windows ACPI and the SPI transport investigation. It replaces the unsuccessful I2C touchscreen experiment; it is not the LKML I2C proposal.
- `0004`, `0005`: Local 2026-09-15 SPI HID power-lifecycle, GPIO ownership and DRM panel follower changes. These extend the first three patches and must be applied as a set.

The original three-patch maintenance archive is [ItsLucas/surface-laptop-7-linux-maintenance](https://github.com/ItsLucas/surface-laptop-7-linux-maintenance). Existing patch headers and authorship are retained; no contributor sign-offs are fabricated. Kernel and device-tree changes retain the licenses of their respective upstream files. New CI scripts and tests are provided under GPL-2.0-only.

Ubuntu source, buildinfo versions and download URLs, the exact recipe commit, all patch hashes, public-certificate fingerprint, toolchain inventory and source package checksums are included in each `BUILD.json`. Reproduce using the repository at that commit and the recorded Ubuntu packages. No proprietary firmware is distributed by this pipeline.
