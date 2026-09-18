#!/usr/bin/env python3
"""Migrate the first signed payload release to native packaging, without keys."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from common import run, sha256
from packaging import build_packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    report = json.loads((args.input / 'SIGNING.json').read_text())
    data = json.loads((args.input / 'BUILD.json').read_text())
    release = data['release']
    if not re.fullmatch(r'\d+\.\d+\.\d+-\d+-sl7\.\d+\.\d+', release):
        raise ValueError('Unexpected kernel release')
    if not re.fullmatch(r'[0-9][a-zA-Z0-9.+:~_-]*', args.version):
        raise ValueError('Invalid package version')
    if (report['release'] != release or report['source_commit'] != data['source_commit']
            or not report['signed'] or not report['all_module_signatures_verified']
            or not report['inner_and_outer_efi_signatures_verified']):
        raise ValueError('Input is not a verified signed build')
    expected_name = f"linux-image-{release}_{data['package_version']}_arm64.deb"
    if report['package'] != expected_name:
        raise ValueError('Unexpected input package')
    source = args.input / expected_name
    if sha256(source) != report['sha256']:
        raise ValueError('Input package hash mismatch')
    run(['dpkg', '--compare-versions', args.version, 'gt', data['package_version']])
    args.output.mkdir(parents=True, exist_ok=False)
    stage = args.output / 'package'
    run(['dpkg-deb', '-x', source, stage])
    before = {str(p.relative_to(stage)): sha256(p) for p in (stage / 'lib/modules').rglob('*') if p.is_file()}
    old_boot = stage / 'boot/sl7' / release
    image = old_boot / 'kernel.efi'
    metadata = stage / 'usr/share/sl7-kernel' / release
    boot_cert = metadata / 'boot-cert.pem'
    der = subprocess.check_output(['openssl', 'x509', '-in', str(boot_cert), '-outform', 'DER'])
    if hashlib.sha256(der).hexdigest() != report['certificates_sha256_der']['boot-cert.pem']:
        raise ValueError('Boot certificate mismatch')
    run(['sbverify', '--cert', boot_cert, image])
    (metadata / 'boot-cert.der').write_bytes(der)
    image_hash = sha256(image)
    for old, new in [('kernel.efi', 'vmlinuz'), ('config', 'config'), ('System.map', 'System.map')]:
        (old_boot / old).rename(stage / 'boot' / (new + '-' + release))
    old_boot.rmdir()
    old_boot.parent.rmdir()
    if image_hash != sha256(stage / 'boot' / ('vmlinuz-' + release)):
        raise ValueError('EFI image changed')
    original_version = data['package_version']
    data['package_version'] = args.version
    packages = build_packages(stage, args.output, data)
    after = {str(p.relative_to(stage)): sha256(p) for p in (stage / 'lib/modules').rglob('*') if p.is_file()}
    if before != after:
        raise ValueError('Module files changed')
    new_image, = [p for p in packages if p.name.startswith('linux-image-')]
    report.update(package=new_image.name, sha256=sha256(new_image),
                  packages={p.name: sha256(p) for p in packages},
                  installation='ubuntu-kernel-hooks-dracut-grub',
                  repackaged_from={'package': source.name, 'sha256': sha256(source),
                                   'version': original_version},
                  payload_unchanged=True)
    (args.output / 'SIGNING.json').write_text(json.dumps(report, indent=2) + '\n')
    shutil.copy2(args.input / 'BUILD.json', args.output / 'BUILD.json')
    (args.output / 'SHA256SUMS').write_text(''.join(sha256(p) + '  ' + p.name + '\n' for p in packages))


if __name__ == '__main__':
    main()
