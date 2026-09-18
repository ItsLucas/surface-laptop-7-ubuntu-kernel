#!/usr/bin/env python3
"""Verify and sign a downloaded bundle locally. Creates a deb; never installs it."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from common import run, sha256, verify_files
from packaging import build_packages


def cert_der(path):
    return subprocess.check_output(['openssl', 'x509', '-in', str(path), '-outform', 'DER'])


def matches_key(cert, key):
    public_cert = subprocess.check_output(['openssl', 'x509', '-in', str(cert), '-pubkey', '-noout'])
    public_key = subprocess.check_output(['openssl', 'pkey', '-in', str(key), '-pubout'])
    if public_cert != public_key:
        raise ValueError('Signing key does not match the public certificate')


def sign_module(path, sign_file, key, cert, release):
    data = path.read_bytes()
    if data[:4] != b'\x7fELF' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('Not an ARM64 ELF module: ' + str(path))
    if b'vermagic=' + release.encode() + b' ' not in data or data.endswith(b'~Module signature appended~\n'):
        raise ValueError('Unexpected module release or existing signature')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Ubuntu kmodsign expects DER; CMS verification below uses the PEM certificate.
        (tmp / 'certificate.der').write_bytes(cert_der(cert))
        run([sign_file, 'sha512', key, tmp / 'certificate.der', path])
        signed = path.read_bytes()
        marker = b'~Module signature appended~\n'
        if not signed.endswith(marker):
            raise ValueError('Missing appended module signature')
        trailer = signed[-len(marker)-12:-len(marker)]
        signature_size = int.from_bytes(trailer[8:12], 'big')
        signature_start = len(signed) - len(marker) - 12 - signature_size
        if signed[:signature_start] != data:
            raise ValueError('Module payload changed while signing')
        (tmp / 'payload').write_bytes(data)
        (tmp / 'signature').write_bytes(signed[signature_start:signature_start+signature_size])
        run(['openssl', 'cms', '-verify', '-binary', '-inform', 'DER', '-in', tmp / 'signature',
             '-content', tmp / 'payload', '-certfile', cert, '-nointern', '-noverify', '-out', os.devnull],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    run(['zstd', '-q', '-8', '--rm', '--', path])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bundle', type=Path, required=True, help='Already extracted unsigned bundle directory')
    ap.add_argument('--output', type=Path, required=True, help='A new output directory')
    ap.add_argument('--module-key', type=Path, required=True)
    ap.add_argument('--module-cert', type=Path, required=True, help='PEM certificate matching the CI public certificate')
    ap.add_argument('--boot-key', type=Path, required=True)
    ap.add_argument('--boot-cert', type=Path, required=True, help='Already enrolled boot-signing PEM certificate')
    ap.add_argument('--sign-file', type=Path, default=Path('/usr/bin/kmodsign'),
                    help='Trusted local signing tool; do not execute a downloaded build helper with private keys')
    args = ap.parse_args()
    bundle = args.bundle.resolve(); out = args.output.resolve()
    verify_files(bundle)
    data = json.loads((bundle / 'BUILD.json').read_text())
    release = data['release']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-[0-9]+-sl7\.[0-9]+\.[0-9]+', release):
        raise ValueError('Invalid kernel release')
    if not re.fullmatch(r'[0-9][a-zA-Z0-9.+:~_-]*', data['package_version']):
        raise ValueError('Invalid package version')
    if data['signed'] or data['hardware_tested']:
        raise ValueError('Expected an unsigned CI candidate')
    if hashlib.sha256(cert_der(args.module_cert)).hexdigest() != data['module_cert_der_sha256']:
        raise ValueError('Kernel trusts a different module certificate; rebuild with your public certificate')
    matches_key(args.module_cert, args.module_key); matches_key(args.boot_cert, args.boot_key)
    if out.exists():
        raise ValueError('Output must be new; no existing files will be overwritten')
    out.mkdir(parents=True)
    stage = out / 'package'
    shutil.copytree(bundle / 'root', stage)
    modules = stage / 'lib/modules' / release
    paths = sorted(modules.rglob('*.ko'))
    if len(paths) != data['module_count']:
        raise ValueError('Module count mismatch')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda p: sign_module(p, args.sign_file, args.module_key,
                                              args.module_cert, release), paths))
    run(['depmod', '-b', stage, release])
    boot = stage / 'boot'; boot.mkdir(parents=True)
    inner = out / 'inner-signed.efi'
    run(['sbsign', '--key', args.boot_key, '--cert', args.boot_cert, '--output', inner,
         bundle / 'boot-inputs/inner-unsigned.efi'])
    run(['sbverify', '--cert', args.boot_cert, inner])
    hwids = out / 'hwids'; hwids.mkdir()
    stubble = bundle / 'stubble/usr'
    shutil.copy2(stubble / 'share/stubble/hwids/x1e80100-microsoft-romulus13.json', hwids)
    unsigned = out / 'outer-unsigned.efi'
    run(['python3', stubble / 'bin/stubblify', 'build', '--stub=' + str(stubble / 'lib/stubble/stubble.efi'),
         '--linux=' + str(inner), '--devicetree-auto=' + str(bundle / 'boot-inputs/romulus13.dtb'),
         '--hwids=' + str(hwids), '--uname=' + release, '--no-sign-kernel', '--output=' + str(unsigned)])
    image = boot / ('vmlinuz-' + release)
    run(['sbsign', '--key', args.boot_key, '--cert', args.boot_cert, '--output', image, unsigned])
    run(['sbverify', '--cert', args.boot_cert, image])
    for name in ['config', 'System.map']:
        shutil.copy2(bundle / 'boot-inputs' / name, boot / (name + '-' + release))
    metadata = stage / 'usr/share/sl7-kernel' / release; metadata.mkdir(parents=True)
    shutil.copy2(bundle / 'BUILD.json', metadata)
    shutil.copy2(args.module_cert, metadata / 'module-cert.pem')
    shutil.copy2(args.boot_cert, metadata / 'boot-cert.pem')
    (metadata / 'boot-cert.der').write_bytes(cert_der(args.boot_cert))
    packages = build_packages(stage, out, data)
    (out / 'SHA256SUMS').write_text(''.join(sha256(p) + '  ' + p.name + '\n' for p in packages))
    print('Packages built:', ', '.join(p.name for p in packages))
    print('No installation was performed. Installing these packages generates initrd and updates GRUB.')


if __name__ == '__main__':
    main()
