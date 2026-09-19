#!/usr/bin/env python3
"""Read hwmon power and record manual suspend/resume; never initiates sleep."""
import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--duration', type=float, default=120)
    parser.add_argument('--stop-after-resume', type=int, default=0,
                        help='Stop after this many valid post-resume samples')
    args = parser.parse_args()
    if not 1 <= args.duration <= 1200 or not 0 <= args.stop_after_resume <= 120:
        parser.error('duration must be 1..1200 seconds; post-resume samples 0..120')
    end = time.monotonic() + args.duration
    last_sleep_clock = None
    resumed = False
    post_resume = 0
    with args.output.open('x') as stream:
        while time.monotonic() < end:
            boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            mono = time.monotonic_ns()
            sleep_clock = boot - mono
            gap = 0 if last_sleep_clock is None else (sleep_clock - last_sleep_clock) / 1e9
            last_sleep_clock = sleep_clock
            if gap > 0.5:
                resumed = True
                post_resume = 0
            row = {'wall_time_ns': time.time_ns(), 'boottime_ns': boot,
                   'monotonic_ns': mono, 'sleep_elapsed_s': max(0, gap)}
            try:
                device = next(p for p in Path('/sys/class/hwmon').iterdir()
                              if (p / 'name').read_text().strip() == 'qcom_pld_power')
                row['power_uW'] = {
                    (device / f'power{i}_label').read_text().strip():
                    int((device / f'power{i}_average').read_text())
                    for i in range(1, 8)
                }
                if resumed:
                    post_resume += 1
            except (OSError, ValueError, StopIteration) as error:
                row['error'] = str(error)
            row['read_duration_s'] = (time.monotonic_ns() - mono) / 1e9
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            if args.stop_after_resume and post_resume >= args.stop_after_resume:
                break
            time.sleep(1)


if __name__ == '__main__':
    main()
