# PLD power validation record

2026-09-19; Surface Laptop 7 13.8-inch / Romulus13, X1E-80-100,
BIOS 175.235.235, Linux 7.3.0-5-sl7.8.1, Secure Boot enabled.
This is an experimental, tested-platform feature, not a general X1E support claim.

## Completed checks

- Read-only diagnostic: 390 snapshots covering both rings. All passed repeated
  producer-counter/data comparisons; no all-zero records or 0xffff power fields.
- Three separate eight-second CPU affinity loads mapped CPUs 0–3, 4–7 and 8–11
  to firmware CPU_CLUSTER_0, 1 and 2. The loaded channels averaged approximately
  18.4, 20.5 and 19.7 W by the Windows-derived scale and fell after each load.
  These are workload observations, not calibrated efficiency benchmarks.
- A separate 14-second window comparison supports the one-second averaging
  interface; see the protocol document for the errors and limitations.
- Driver build against the running kernel ABI with `W=1 KCFLAGS=-Werror`.
- Module signatures verified against the enrolled local MOK; ordinary kernel
  loading succeeded under integrity lockdown without forced versions.
- Unprivileged `sensors` text and JSON output; seven read-only average/interval/
  label sets, correct µW conversion and one-second interval presentation.
- Initial implementation: four concurrent readers, device/module removal and reload, 525 successful
  reads, no stuck reader, stale hwmon instance, or leaked resource claim.
- Exact protocol/freshness helpers tested under ASan/UBSan, including torn reads,
  conversion bounds, u32 wrap, stale/infrequent reads and counter resets.
- Kernel style checks reported no errors or warnings for the driver sources.
- An unsigned module build and separate `modules_install` staging check verified
  the two expected uncompressed modules under `updates/sl7`, ready for CI signing.
- The repository's 23 local tests pass. The dpkg/dracut/GRUB container check runs
  in GitHub Actions; Docker is not installed on the development laptop.
- The board DMI alias resolves to `sl7_pld_device`; its soft dependency resolves
  to `qcom_pld_power`. Automatic loading during an actual cold boot is not yet tested.

## Manual suspend/resume

The initial implementation passed an 18.6-second manual suspend: the first
post-resume access returned `ENODATA`, followed by ten valid samples. Its
synchronous priming delay was replaced with deferrable asynchronous refresh
after a user noticed the pause in `sensors`.

The revised worker lifecycle passed a second, 14.8-second manual suspend.
Two initial accesses returned `ENODATA`, then ten consecutive samples were valid.
The longest post-resume read took about 2.51 ms. Seventeen separate unprivileged
`sensors -j` runs, including 4.2-second gaps, had no errors and a maximum wall time
of 10.13 ms including process startup (median 8.54 ms). This validates the worker's
suspend/resume behavior on this firmware; Linux-only cold startup remains open.
A subsequent small cached-error helper change preserves `EIO` and adds explicit
validity checks; its paths are covered by the shared-helper tests, without claiming
that every later source edit was part of the same physical sleep test.

The same system resume logged a mac80211 rate-statistics WARN. Wi-Fi remained
connected and no PLD stack or Oops was observed; this is recorded separately from
the power-driver result rather than claiming the entire system resume was clean.

To record a manual test without initiating sleep:

```sh
python3 tools/monitor-pld-power.py --output power-resume.jsonl \
  --duration 1200 --stop-after-resume 10
```

Put the machine to sleep manually, then wake it. The tool records hwmon readings,
errors, read duration and the difference between CLOCK_BOOTTIME and
CLOCK_MONOTONIC to identify suspended time. Review local logs before sharing;
raw machine-specific captures are not part of this public repository.

## Still unverified

Linux-only cold startup; external power-meter calibration; dedicated GPU load;
battery/USB rail semantics; other Surface sizes, firmware versions and X1E devices.
Failure behavior for torn/stalled firmware records is exercised with fake I/O;
the tests do not intentionally corrupt live shared memory.

A user reported audible fan operation at roughly 3000 RPM with CPU temperatures
around 38–40°C. Removing both PLD modules for one minute did not stop it (mean
3001.5 RPM); reloading them for a further 30 seconds gave 3000.2 RPM. This
does not establish a cause; fan behavior after a reboot remains to be observed.
The power driver has no fan-control writes, and no fan curve was modified.
