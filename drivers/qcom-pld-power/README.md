# Qualcomm X1E PLD power telemetry (experimental)

These GPL-2.0-only modules expose firmware power readings through Linux hwmon.
They do not set power limits, write firmware memory, or implement hardware energy
counters. Protocol details are documented in [PROTOCOL.md](PROTOCOL.md).

## Supported and tested system

- Surface Laptop 7 **13.8-inch / Romulus13**, X1E-80-100.
- Firmware **175.235.235**. The local device bridge rejects other firmware versions
  and checks both the DMI identity and root device-tree compatible strings.
- Linux **7.3.0-5-sl7.8.1**, arm64, Secure Boot and integrity lockdown enabled.
- The documented memory resource must be EFI reserved memory, disjoint from
  System RAM, and available for exclusive reservation. Missing EFI metadata or
  conflicting ownership causes probe to fail.

This is not a claim of support for every X Elite laptop, Surface Laptop 7 size,
firmware revision, or future kernel. Do not bypass the platform checks to try it
on another device. Contributions that extend support need resource and protocol
evidence from the proposed platform.

## Architecture

`qcom_pld_power` is a resource-based platform hwmon driver. It maps the supplied
24 KiB resource read-only, non-executable and uncached. Its only hardware accesses
read the one-second ring's producer counter and seven power fields. There are no
arbitrary address parameters, raw memory interfaces, or firmware calls.
A deferrable delayed work item refreshes the cache once a second when the CPU is
awake; the timer does not wake an idle CPU solely for telemetry.

`sl7_pld_device` is a separate, deliberately narrow board bridge. Upstream removed
the redundant DT reservation because EFI already reserves the region, but the
stock DT does not describe a power-meter device. The bridge supplies the observed
resource without modifying DT or the boot image. A matching DMI modalias enables
ordinary udev/module loading; the SL7 support package also requests loading via
`modules-load.d`. A soft dependency loads the hwmon driver first.
Its runtime OF checks also reject the 15-inch model even if DMI strings overlap.

The provisional `qcom,x1e80100-pld-power` OF match is for a future explicit device
description, not a published upstream binding. The bridge refuses to create a
second device when that compatible already exists. Upstream submission will need
a reviewed resource/binding design; this repository does not invent a stable
firmware ABI from one tested firmware revision.

## Reading the data

Once installed by a kernel release containing these modules:

```sh
sudo modprobe sl7_pld_device
sensors 'qcom_pld_power-*'
watch -n 2 'sensors qcom_pld_power-*'
```

No `sensors-detect`, root access for readings, or lm-sensors code change is needed.
`sensors` may call the platform device an “ISA adapter”; that is its generic
platform-device presentation, not evidence of a physical ISA bus.

| hwmon channels | Labels |
|---|---|
| power1–3 | CPU_CLUSTER_0, CPU_CLUSTER_1, CPU_CLUSTER_2 |
| power4 | GPU |
| power5–7 | PSU_USB, USBC_TOTAL, SYS |

Each channel provides read-only `powerN_average` (µW),
`powerN_average_interval` (1000 ms), and `powerN_label`.
`update_interval` is also read-only and reports 1000 ms. The driver exposes the
firmware's one-second average, not an instantaneous `powerN_input` or a fabricated
`energyN_input`. The firmware's averaging kernel and absolute accuracy are not
formally specified; see the experimental comparison in PROTOCOL.md.

The CPU channels were mapped by controlled affinity tests: CPUs 0–3, 4–7 and
8–11 respectively. This mapping describes the tested machine. SYS is not a CPU
package value, and SYS/PSU_USB must not be added together. GPU and USBC_TOTAL were
present in Windows metadata; dedicated GPU and battery/USB rail validation is
still outstanding.

## Freshness, errors and sleep

Reads use the cached seven-channel snapshot and never wait for a firmware tick.
The firmware continues to update independently; loading the driver does not
enable or accelerate it. A freezable workqueue updates the cache via a deferrable
one-second timer. If idle CPUs defer it long enough for data to expire, a reader
requests an asynchronous refresh, rate-limited to once per 100 ms.

The worker requires an observed producer-counter advance before accepting
retained data. The same requirement applies after resume, a sampling gap over
three seconds, counter reset, or an implausible counter jump. Until it sees fresh
data, sysfs returns `ENODATA` immediately; shortly after load/resume, `sensors` can
therefore briefly report unavailable readings. Valid repeated heads are tolerated
within the three-second freshness bound. The bound uses the previous observation
time, not the moment a changed counter is noticed.

Each snapshot reads the producer counter three times and the fields twice, with
at most four attempts. Unstable samples return `EIO`; invalid 0xffff fields or
stalled/unprimed data return `ENODATA`. Zero is a valid power reading if the
producer is alive. Unsigned counter wrap is supported. These checks reduce
publication races but cannot replace an official firmware memory-ordering spec.

A PM notifier cancels sampling before system sleep and invalidates all cached
values on resume. Cleanup synchronously cancels work before releasing memory.
It does not initiate sleep or change device power states. No energy integration
spans suspend. The live manual-resume test status is in
[the validation record](../../docs/pld-power-validation.md).

## Build and signing

GitHub Actions builds both external modules against the exact generated Ubuntu
kernel output, with `W=1 KCFLAGS=-Werror`, and includes them under
`updates/sl7` in the kernel package. They pass through the existing module-signing
step. Driver source changes participate in the build recipe hash and trigger a
new kernel build; API/build failures use the existing failure notification path.
These external modules set Linux's normal out-of-tree taint flag.

For local development, use an arm64 build tree prepared for the **exact running
kernel**. Generic headers for a different kernel release are not interchangeable.
The prebuilt SL7 image does not currently include a kernel-header package.

```sh
# Run from this driver's directory; set KDIR to the matching prepared build tree.
make -C "$KDIR" M="$PWD" MO="$PWD/../../../work/pld-build" W=1 KCFLAGS=-Werror modules
```

Sign both resulting `.ko` files with a key trusted by the target kernel before
installing on a Secure Boot system. Never disable signature enforcement or force
module-version mismatches. The public repository contains no signing private key.
The regular signed kernel/APT release is the supported delivery path; the local
module-only package used for development is specific to its kernel release.

## Tests and removal

From the repository root:

```sh
python3 -m unittest discover -s tests -p test_pld_power.py -v
```

The C tests compile the same protocol/freshness helpers used by the driver with
ASan/UBSan. Fake I/O covers torn head/data publications, bounded retries, offsets,
unit conversion, sentinels and wrap. Freshness tests cover startup, stalling,
infrequent reads, backward/forward resets, clock regression and resume invalidation.
They perform no hardware accesses and need no root. They do not claim to validate
kernel locking or real suspend; those require the separate live checks.

```sh
sudo modprobe -r sl7_pld_device qcom_pld_power
```

Unloading removes hwmon, the worker, PM notifier, mapping and resource claim. To disable
future automatic loading while retaining the files, remove/disable the local
`modules-load.d/sl7-pld-power.conf` request and blacklist `sl7_pld_device` in a
local modprobe configuration. There is no initramfs or GRUB dependency.
