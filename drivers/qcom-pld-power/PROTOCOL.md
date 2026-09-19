# PLD power protocol: evidence and remaining questions

This document records independently observed interface facts. Windows binaries,
disassembly and device-specific raw captures are not redistributed here.

## Evidence chain

On the tested Romulus13, Windows Energy Meter exposes seven channels through the
standard EMI interface on the Qualcomm PEP device (`QCOM0C17`). The provider uses
`umpoext.dll`; Qualcomm's [libqcperf POWER backend](https://github.com/qualcomm/libqcperf/blob/662b0c3cddfd7c92d71fcc16fafdcc1b342047b7/qcperf/backends/wos-power-backend/power-telemetry/src/power_telemetry.c)
reads the Energy Meter PDH counters. EMI v2 metadata names Qualcomm / 8380 and the
seven channels listed below.

Local static inspection of `qcpep8380.sys` version 1.0.0.25705
(SHA256 `e5bdeb8c0fb8823990f7520a19c00807711cf909f91f8d67db78ffb18c1b2277`)
identified these facts; all addresses in this paragraph are file RVAs:

- Initialization at 0xa4788 maps physical **0x81f30000**, length **0x6000**, using
  `MmMapIoSpaceEx` with **0x202 = PAGE_READONLY | PAGE_NOCACHE**.
- The callback table at 0x2b8c40 selects the seven channel readers.
- Property table 0x2b96d0, entry 0xad, names
  `PowerPollingTimeDurationMilliSeconds`, with a compiled default of 1000.
  Values below 500 normalize to 100; other values normalize to 1000.
  A registry override can change the Windows selection.
- The driver multiplies the u16 power fields by 10, then integrates power and
  elapsed time into EMI energy. The firmware region therefore must not be
  presented as a hardware accumulated-energy counter.

The [Microsoft mapping documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-mmmapiospaceex)
defines the mapping flags. [EMI measurement documentation](https://learn.microsoft.com/en-us/windows/win32/api/emi/ns-emi-emi_channel_measurement_data)
defines energy units and 100 ns time intervals. The observed software formula
`energy_pWh += power_mW * time_100ns / 36` is dimensionally consistent.
Thus each raw count represents **10 mW**, or **10000 µW** for hwmon.

## Memory layout

Offsets are relative to the 24 KiB mapped region. All fields are little-endian.

| Ring | Producer head (u32) | Records | Capacity | Record bytes |
|---|---:|---:|---:|---:|
| ~100 ms | 0x130 | 0x138 | 256 | 40 |
| ~1000 ms | 0x2938 | 0x2940 | 128 | 40 |

The head continues beyond ring capacity. The latest slot is `(head - 1) % capacity`.

| Channel | Callback RVA | u16 offset within record |
|---|---:|---:|
| CPU_CLUSTER_0 | 0xa25e0 | 0x08 |
| CPU_CLUSTER_1 | 0xa26f0 | 0x0a |
| CPU_CLUSTER_2 | 0xa2800 | 0x0c |
| GPU | 0xa2910 | 0x0e |
| PSU_USB | 0xa2b10 | 0x1a |
| USBC_TOTAL | 0xa2c00 | 0x1c |
| SYS | 0xa2a20 | 0x18 |

The hwmon driver reads only the second ring and these fields. Unidentified
record/header bytes are not used or exposed. No reset, control or limit field is
written.

## Temporal resolution versus accuracy

Both rings have the same u16 representation and inferred 10 mW step. Live Linux
sampling observed producer rates of about 10 Hz and 1 Hz. In a separate 14-second
trace with a five-second four-core workload and 20 ms host polling, 13 complete
one-second windows closely matched the preceding ten 100 ms records.

Across the three CPU channels plus SYS and PSU_USB, the mean absolute difference
was about **0.017 W**, with maximum **0.183 W** near a transition. Shifting the
comparison by one 100 ms record increased the error substantially. This supports
exposing the one-second record as `powerN_average` with a 1000 ms interval.
It does not establish the exact averaging kernel, an accuracy specification, or
whether the underlying firmware uses physical rail measurements or a power model.
The two rings should not be described as different measurement precision levels
merely because one is smoother.

## Linux resource ownership

Linux [commit 7d240c5](https://github.com/torvalds/linux/commit/7d240c5dd34ae8560f8d0557fbbd7b0165eab486)
removed the redundant `pld-pep` DT reservation because EFI already reserves it.
On the tested firmware, EFI reports 0x81f30000–0x81f37fff as reserved, and
`/proc/iomem` includes the region in a reserved span. The driver requires a
retained, covering EFI descriptor, checks for System RAM conflicts and claims the
resource before mapping it.

This PLD ring is not the [Glymur SPEL powercap interface](https://lists.openwall.net/linux-kernel/2026/07/02/2093).
Neither SPEL addresses nor its accumulated-energy register format are reused.

## Unresolved points

- Official publication/cache ordering and record version/validity metadata.
- Cold Linux-only startup, without a preceding Windows boot.
- GPU load response and battery-only/USB rail coverage.
- Whether SYS overlaps particular rails; it equals PSU_USB in the tested
  external-power, non-charging state. Do not add them.
- Absolute calibration and whether the values are measured or modeled by firmware.
- Support for additional hardware/firmware, requiring explicit evidence.

The checks and conservative platform bridge limit the current implementation;
they are not a substitute for documenting these unknowns.
