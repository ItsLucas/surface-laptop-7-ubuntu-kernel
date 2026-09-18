"""Build normal APT kernel packages without running any installation hooks."""
from pathlib import Path
import shutil
from common import run


TEMPLATES = Path(__file__).resolve().parent / 'package-files'


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
    control(support, 'linux-sl7-support', version, 'all', 'dracut, grub2-common',
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
