#!/usr/bin/env python3
"""Real dpkg/dracut/GRUB lifecycle in a disposable container; no boot test.

Only the block-device probe and container detection are simulated. Generated
fixture modules are ELF files for the container's CPU, not runnable drivers.
--packages additionally exercises an actual release's three debs.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from packaging import build_packages
from pe_fixture import image_with_dtb


def run(*args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)


def write(path, contents, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    path.chmod(mode)


def simulate_devices():
    write('/etc/flash-kernel/machine', 'Microsoft Surface Laptop 7 (13.8 inch)\n')
    write('/usr/sbin/grub-probe', '''#!/usr/bin/python3
import sys
a = sys.argv[1:]
target = next((x.split('=', 1)[1] for x in a if x.startswith('--target=')), None)
if target is None:
    for flag in ['-t', '--target']:
        if flag in a: target = a[a.index(flag) + 1]
values = {'device':'/dev/vda1', 'fs':'ext2', 'fs_uuid':'11111111-2222-3333-4444-555555555555',
          'partuuid':'11111111-01', 'drive':'(hd0,gpt1)', 'partmap':'gpt',
          'compatibility_hint':'hd0,gpt1', 'hints_string':'--hint=hd0,gpt1',
          'abstraction':'', 'cryptodisk_uuid':''}
if target not in values: raise SystemExit('Unhandled probe: ' + repr(a))
print(values[target])
''', 0o755)
    write('/usr/bin/systemd-detect-virt', '#!/bin/sh\nexit 1\n', 0o755)
    write('/dev/vda1', '')
    by_uuid = Path('/dev/disk/by-uuid/11111111-2222-3333-4444-555555555555')
    by_uuid.parent.mkdir(parents=True, exist_ok=True)
    by_uuid.symlink_to('/dev/vda1')
    write('/etc/fstab', 'UUID=11111111-2222-3333-4444-555555555555 / ext4 defaults 0 1\n')
    write('/etc/default/grub', 'GRUB_DEFAULT=sl7-spi-touchscreen-test\nGRUB_TIMEOUT=5\n'
          'GRUB_DISABLE_OS_PROBER=true\nGRUB_CMDLINE_LINUX="clk_ignore_unused pd_ignore_unused cma=128M efi=noruntime"\n')
    write('/boot/grub/grub.cfg', '# previous boot menu\n')
    write('/usr/lib/firmware/updates/ath12k/WCN7850/hw2.0/board-2.bin', 'local-board-override\n')


def fixture(release, version):
    out = Path('/tmp/sl7-smoke') / release
    stage = out / 'package'
    modules = stage / 'lib/modules' / release
    modules.mkdir(parents=True)
    for name in ['spi-hid', 'spi-geni-qcom', 'gpi']:
        source = out / (name + '.c')
        source.write_text(f'__attribute__((section(".modinfo"))) const char info[] = '
                          f'"vermagic={release} SMP\\0depends=\\0license=GPL\\0";\n')
        run('gcc', '-c', '-o', modules / (name + '.ko'), source)
    for name in ['modules.builtin', 'modules.builtin.modinfo', 'modules.order']:
        (modules / name).write_text('')
    image, _ = image_with_dtb()
    kernel = stage / ('boot/vmlinuz-' + release)
    kernel.parent.mkdir(parents=True, exist_ok=True)
    kernel.write_bytes(image)
    write(stage / ('boot/System.map-' + release), '')
    write(stage / ('boot/config-' + release), 'CONFIG_BLK_DEV_INITRD=y\nCONFIG_RD_ZSTD=y\nCONFIG_MODULES=y\n')
    return build_packages(stage, out, {'release': release, 'package_version': version})


def install(packages, check=True):
    ordered = sorted(packages, key=lambda p: (0 if p.name.startswith('linux-sl7-support_') else
                                             2 if p.name.startswith('linux-sl7_') else 1))
    result = subprocess.run(['dpkg', '--force-architecture', '-i', *map(str, ordered)])
    if check:
        result.check_returncode()
    return result


def assert_installed(release):
    dtb = 'qcom/x1e80100-microsoft-romulus13.dtb'
    provided = Path('/usr/lib/linux-image-' + release) / dtb
    installed = Path('/boot/dtbs') / release / dtb
    assert provided.is_file() and installed.read_bytes() == provided.read_bytes()
    initrd = Path('/boot/initrd.img-' + release)
    assert initrd.stat().st_size > 0
    contents = subprocess.check_output(['lsinitrd', str(initrd)], text=True)
    assert 'spi-hid.ko' in contents and 'spi-geni-qcom.ko' in contents and 'gpi.ko' in contents
    assert 'board-2.bin' in contents
    menu = Path('/boot/grub/grub.cfg').read_text()
    assert 'vmlinuz-' + release in menu and 'initrd.img-' + release in menu
    assert 'set default="0"' in menu
    assert 'clk_ignore_unused pd_ignore_unused cma=128M efi=noruntime' in menu
    assert '11111111-2222-3333-4444-555555555555' in menu
    if Path('/etc/default/grub.d/zz-sl7-apt-follow.cfg').exists():
        first_entry = menu.split("menuentry ", 1)[1].split('\n}', 1)[0]
        assert 'vmlinuz-' + release in first_entry
        assert 'devicetree' not in first_entry
    # A deferred flash-kernel trigger can recreate aliases after GRUB ran.
    # A later manual regeneration must clean them again and keep the real DTB.
    run('update-grub')
    regenerated = Path('/boot/grub/grub.cfg').read_text()
    first_entry = regenerated.split("menuentry ", 1)[1].split('\n}', 1)[0]
    assert 'vmlinuz-' + release in first_entry and 'devicetree' not in first_entry
    assert not Path('/boot/dtb-' + release).is_symlink()
    assert not Path('/boot/dtb').is_symlink()
    run('grub-script-check', '/boot/grub/grub.cfg')
    return regenerated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or os.geteuid() != 0:
        raise SystemExit('Run only as root in a disposable container with no host boot/device mounts')
    simulate_devices()
    first, second = '7.1.0-1-sl7.900.1', '7.1.0-1-sl7.901.1'
    write('/etc/default/grub.d/zz-sl7-apt-follow.cfg', 'SL7_FOLLOW_APT=1\n')
    # A newer stock kernel must remain available without displacing SL7.
    generic_image, generic_dtb = image_with_dtb()
    Path('/boot/vmlinuz-9.9.0-99-generic').write_bytes(generic_image)
    write('/boot/initrd.img-9.9.0-99-generic', 'stock-fallback-fixture\n')
    stock_dtb = Path('/usr/lib/linux-image-9.9.0-99-generic/qcom/x1e80100-microsoft-romulus13.dtb')
    stock_dtb.parent.mkdir(parents=True)
    stock_dtb.write_bytes(generic_dtb)
    install(fixture(first, '7.1.0-1.1+sl7.900.1'))
    before = assert_installed(first)
    second_packages = fixture(second, '7.1.0-1.1+sl7.901.1')
    failure_hook = Path('/etc/kernel/postinst.d/00-fail-sl7-test')
    write(failure_hook, '#!/bin/sh\nexit 42\n', 0o755)
    assert install(second_packages, check=False).returncode != 0
    assert Path('/boot/grub/grub.cfg').read_text() == before
    failure_hook.unlink()
    run('dpkg', '--configure', '-a')
    assert_installed(second)
    assert Path('/boot/initrd.img-' + first).exists()
    run('dpkg-reconfigure', '-f', 'noninteractive', 'linux-image-' + second)
    assert_installed(second)
    run('dpkg', '--remove', 'linux-sl7')
    run('dpkg', '--purge', 'linux-image-' + second)
    assert not Path('/boot/initrd.img-' + second).exists()
    assert second not in Path('/boot/grub/grub.cfg').read_text()
    assert_installed(first)
    if args.packages:
        packages = sorted(args.packages.glob('*.deb'))
        report = json.loads((args.packages / 'SIGNING.json').read_text())
        release = report['release']
        install(packages)
        assert_installed(release)
        run('dpkg-reconfigure', '-f', 'noninteractive', 'linux-image-' + release)
        assert_installed(release)
        run('dpkg', '--remove', 'linux-sl7')
        run('dpkg', '--purge', 'linux-image-' + release)
        assert not Path('/boot/initrd.img-' + release).exists()
        assert release not in Path('/boot/grub/grub.cfg').read_text()
        assert_installed(first)
    print('PASS: install, initrd contents, GRUB, failed-hook recovery, reconfigure, coexistence and purge')


if __name__ == '__main__':
    main()
