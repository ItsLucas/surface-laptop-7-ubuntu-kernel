"""Build normal APT kernel packages without running any installation hooks."""
from pathlib import Path
import shutil
import struct
from common import run


TEMPLATES = Path(__file__).resolve().parent / 'package-files'
ROMULUS_DTB = 'qcom/x1e80100-microsoft-romulus13.dtb'


def embedded_dtb(image):
    """Read the DTB already covered by the Stubble PE signature, including its exact FDT size."""
    data = Path(image).read_bytes()
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Expected a signed ARM64 Stubble PE image')
    pe_offset = struct.unpack_from('<I', data, 0x3c)[0]
    if pe_offset + 24 > len(data) or data[pe_offset:pe_offset + 4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    machine, section_count = struct.unpack_from('<HH', data, pe_offset + 4)
    optional_size = struct.unpack_from('<H', data, pe_offset + 20)[0]
    table = pe_offset + 24 + optional_size
    if machine != 0xaa64 or table + section_count * 40 > len(data):
        raise ValueError('Invalid ARM64 PE section table')
    trees = []
    for offset in range(table, table + section_count * 40, 40):
        if data[offset:offset + 8].rstrip(b'\0') != b'.dtbauto':
            continue
        virtual_size, _, raw_size, raw_offset = struct.unpack_from('<IIII', data, offset + 8)
        if raw_offset + raw_size > len(data) or virtual_size > raw_size or virtual_size < 40:
            raise ValueError('Invalid embedded device-tree bounds')
        blob = data[raw_offset:raw_offset + virtual_size]
        magic, total_size = struct.unpack_from('>II', blob)
        if magic != 0xd00dfeed or total_size != virtual_size:
            raise ValueError('Invalid embedded FDT header or size')
        if b'microsoft,romulus13\0' not in blob:
            raise ValueError('Embedded device tree is not for Romulus13')
        trees.append(blob)
    if len(trees) != 1:
        raise ValueError('Expected exactly one Romulus13 .dtbauto section')
    return trees[0]


def stage_dtb(stage, release):
    """Satisfy flash-kernel without modifying the signed EFI image or its embedded DTB."""
    blob = embedded_dtb(stage / 'boot' / ('vmlinuz-' + release))
    target = stage / ('usr/lib/linux-image-' + release) / ROMULUS_DTB
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    target.chmod(0o644)
    return target


def control(stage, name, version, architecture, depends, description):
    directory = stage / 'DEBIAN'
    directory.mkdir(parents=True, exist_ok=True)
    size = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file()) // 1024 + 1
    (directory / 'control').write_text(f'''Package: {name}
Version: {version}
Architecture: {architecture}
Maintainer: SL7 kernel maintainers <noreply@localhost>
Section: kernel
Priority: optional
Installed-Size: {size}
Depends: {depends}
Description: {description}
''')


def build_deb(stage, out, name, version, architecture):
    package = out / f'{name}_{version}_{architecture}.deb'
    run(['dpkg-deb', '--build', '--root-owner-group', '-Zzstd', stage, package])
    return package


def build_packages(stage, out, data):
    """stage already contains signed modules and /boot/vmlinuz-RELEASE."""
    release, version = data['release'], data['package_version']
    name = 'linux-image-' + release
    stage_dtb(stage, release)
    control(stage, name, version, 'arm64',
            f'kmod, linux-base (>= 4.17~), debianutils (>= 5.21), dracut, '
            f'linux-sl7-support (>= {version})',
            'Signed Surface Laptop 7 13.8-inch kernel\n'
            ' Includes the Romulus13 device tree and signed modules. Installation\n'
            ' generates an initramfs and updates the existing GRUB configuration.')
    for template in sorted((TEMPLATES / 'image').iterdir()):
        target = stage / 'DEBIAN' / template.name
        target.write_text(template.read_text().replace('@RELEASE@', release))
        target.chmod(0o755)
    image = build_deb(stage, out, name, version, 'arm64')

    support = out / 'support-package'
    shutil.copytree(TEMPLATES / 'support', support)
    control(support, 'linux-sl7-support', version, 'all', 'dracut, grub2-common, python3',
            'Surface Laptop 7 initramfs and GRUB integration\n'
            ' Keeps machine-local firmware and boot arguments, adds the SL7 SPI\n'
            ' drivers to SL7 initramfs images and retains installed SL7 kernels.')
    with (support / 'DEBIAN/control').open('a') as stream:
        stream.write('Multi-Arch: foreign\n')
    (support / 'DEBIAN/conffiles').write_text(''.join(
        '/' + str(p.relative_to(support)) + '\n'
        for p in sorted((support / 'etc').rglob('*')) if p.is_file()))
    support_deb = build_deb(support, out, 'linux-sl7-support', version, 'all')

    meta = out / 'meta-package'
    control(meta, 'linux-sl7', version, 'arm64', f'{name} (= {version})',
            'Latest Surface Laptop 7 13.8-inch kernel\n'
            ' Install this metapackage to follow kernel updates through APT.\n'
            ' Secure Boot requires enrollment of the published boot certificate.')
    meta_deb = build_deb(meta, out, 'linux-sl7', version, 'arm64')
    return [image, support_deb, meta_deb]
