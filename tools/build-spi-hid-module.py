#!/usr/bin/env python3
"""Compile the patched spi-hid transport out of tree against Ubuntu's headers.

A fast pull-request check, not a replacement for the full kernel build. It
takes the drivers/hid/spi-hid/ parts of the series selected for the installed
generic headers' kernel, applies them with the same strict options as the full
build, and builds the module with -Werror so modpost also resolves its symbols.
Run only in a disposable Ubuntu 26.10 container with linux-headers-generic.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
from common import ROOT, patches  # noqa: E402

PREFIX = 'drivers/hid/spi-hid/'


def spi_hid_sections(text):
    """Return the per-file diff sections of text that touch PREFIX."""
    lines = text.splitlines(keepends=True)
    out, keep = [], False
    for i, line in enumerate(lines):
        if line.startswith('diff --git'):
            keep = False
            continue
        if line.startswith('--- ') and i + 1 < len(lines) and lines[i + 1].startswith('+++ '):
            keep = lines[i + 1][4:].split('\t')[0].strip().startswith('b/' + PREFIX)
        if keep:
            out.append(line)
    return ''.join(out)


def compiler(build):
    """The compiler named in the headers' config, so flags match the kernel."""
    text = (build / '.config').read_text()
    match = re.search(r'^CONFIG_CC_VERSION_TEXT="(\S+)', text, re.M)
    if not match:
        raise SystemExit('CONFIG_CC_VERSION_TEXT missing from the headers config')
    cc = match.group(1)
    if not shutil.which(cc):
        raise SystemExit(f'{cc} is not installed; install the matching gcc package')
    return cc


def main():
    builds = sorted(Path('/usr/src').glob('linux-headers-*-generic'))
    if not builds:
        raise SystemExit('linux-headers-*-generic is not installed')
    build = builds[-1]
    kernel = build.name.removeprefix('linux-headers-').split('-')[0]
    cc = compiler(build)
    print(f'headers {build.name}, kernel series {kernel}, compiler {cc}', flush=True)

    with tempfile.TemporaryDirectory(prefix='spi-hid-') as tmp:
        tree = Path(tmp)
        for patch in patches(kernel=kernel):
            part = spi_hid_sections(patch.read_text())
            if not part:
                continue
            subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1'],
                           input=part, text=True, cwd=tree, check=True)
            print(f'applied {patch.relative_to(ROOT)}', flush=True)
        source = tree / PREFIX
        subprocess.run(['make', '-C', str(build), f'M={source}', f'CC={cc}',
                        'CONFIG_SPI_HID=m', 'KCFLAGS=-Werror', 'modules'], check=True)
        module = source / 'spi-hid.ko'
        if not module.is_file():
            raise SystemExit('spi-hid.ko was not produced')
        subprocess.run(['modinfo', str(module)], check=True)


if __name__ == '__main__':
    main()
