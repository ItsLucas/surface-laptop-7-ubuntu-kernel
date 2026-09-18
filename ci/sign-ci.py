#!/usr/bin/env python3
"""Use environment Secrets only in a disposable, network-disabled signing container."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from common import ROOT, run, sha256

SECRET_NAMES = {
    'module-key.pem': 'SL7_MODULE_KEY_PEM',
    'module-cert.pem': 'SL7_MODULE_CERT_PEM',
    'boot-key.pem': 'SL7_BOOT_KEY_PEM',
    'boot-cert.pem': 'SL7_BOOT_CERT_PEM',
}


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('CI signer must run in the disposable signing container')
    downloads = Path('/input'); out = Path('/out')
    run(['sha256sum', '-c', 'SHA256SUMS'], cwd=downloads)
    archives = list(downloads.glob('*-unsigned.tar.zst'))
    if len(archives) != 1:
        raise ValueError('Expected exactly one unsigned build bundle')
    # Secrets live only on container tmpfs, outside artifact directories.
    with tempfile.TemporaryDirectory(prefix='sl7-signing-keys-', dir='/tmp') as secrets_dir:
        keys = Path(secrets_dir)
        for filename, name in SECRET_NAMES.items():
            value = os.environ.pop(name, '')
            if not value or len(value) > 48 * 1024:
                raise ValueError('Missing/invalid signing Secret: ' + name)
            fd = os.open(keys / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(value.strip() + '\n')
            del value
        with tempfile.TemporaryDirectory(prefix='sl7-signing-work-', dir=out) as work_dir:
            work = Path(work_dir)
            # Python's data extraction filter rejects path traversal, device nodes and external links.
            import tarfile
            process = subprocess.Popen(['zstd', '-dc', str(archives[0])], stdout=subprocess.PIPE)
            try:
                with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
                    archive.extractall(work, filter='data')
            finally:
                process.stdout.close()
                if process.wait() != 0:
                    raise RuntimeError('Failed to decompress build bundle')
            bundle, = work.glob('sl7-*-unsigned')
            signed = work / 'signed'
            run(['python3', ROOT / 'ci/sign-local.py', '--bundle', bundle, '--output', signed,
                 '--module-key', keys / 'module-key.pem', '--module-cert', keys / 'module-cert.pem',
                 '--boot-key', keys / 'boot-key.pem', '--boot-cert', keys / 'boot-cert.pem',
                 '--sign-file', '/usr/bin/kmodsign'])
            packages = sorted(signed.glob('*.deb'))
            if len(packages) != 3:
                raise ValueError('Expected image, support and metapackage')
            package, = signed.glob('linux-image-*.deb')
            for item in packages:
                shutil.copy2(item, out / item.name)
            fingerprints = {}
            for name in ['module-cert.pem', 'boot-cert.pem']:
                der = subprocess.check_output(['openssl', 'x509', '-in', str(keys / name), '-outform', 'DER'])
                import hashlib
                fingerprints[name] = hashlib.sha256(der).hexdigest()
            metadata = json.loads((bundle / 'BUILD.json').read_text())
            report = {'release': metadata['release'], 'source_commit': metadata['source_commit'],
                      'package': package.name, 'sha256': sha256(out / package.name),
                      'packages': {p.name: sha256(out / p.name) for p in packages},
                      'installation': 'ubuntu-kernel-hooks-dracut-grub',
                      'signed': True, 'hardware_tested': False, 'certificates_sha256_der': fingerprints,
                      'module_count': metadata['module_count'], 'all_module_signatures_verified': True,
                      'inner_and_outer_efi_signatures_verified': True,
                      'private_keys_in_artifacts': False}
            (out / 'SIGNING.json').write_text(json.dumps(report, indent=2) + '\n')
    (out / 'SIGNING-SHA256SUMS').write_text(''.join(sha256(p) + '  ' + p.name + '\n'
        for p in sorted(out.iterdir()) if p.is_file() and p.name != 'SIGNING-SHA256SUMS'))
    print('Signed and verified candidate exported; temporary signing keys removed.')


if __name__ == '__main__':
    main()
