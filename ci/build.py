#!/usr/bin/env python3
"""Build an unsigned, version-isolated ARM64 kernel bundle in the CI container."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from common import ROOT, apply_patches, patches, run, sha256, verify_files


def main():
    if not Path('/.dockerenv').exists() or os.uname().machine != 'aarch64':
        raise SystemExit('Run only inside a disposable ARM64 Ubuntu 26.10 container')
    work = ROOT / 'work'; dist = ROOT / 'dist'
    data = json.loads((work / 'input.json').read_text())
    if not data['should_build']:
        return
    dist.mkdir(exist_ok=True)
    logs = work / 'logs'; logs.mkdir(exist_ok=True)
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
    run(['apt-get', 'build-dep', '-y', '--no-install-recommends', 'linux=' + data['ubuntu_version']], env=env)
    run(['apt-get', 'install', '-y', '--no-install-recommends', 'bc', 'bison', 'flex', 'libelf-dev',
         'libssl-dev', 'dwarves', 'rsync', 'cpio', 'kmod', 'zstd', 'device-tree-compiler', 'stubble',
         'python3-pefile', 'python3-jinja2', 'sbsigntool'], env=env)
    run(['apt-get', 'clean'])
    if shutil.disk_usage(work).free < 25 * 1024**3:
        raise RuntimeError('Less than 25 GiB free before build; increase runner disk capacity')
    downloads = work / 'downloads'; downloads.mkdir()
    for name in [data['source_package'], data['buildinfo_package']]:
        run(['apt-get', 'download', name + '=' + data['inputs'][name]['version']], cwd=downloads)
    data['download_sha256'] = {p.name: sha256(p) for p in downloads.glob('*.deb')}
    source_deb, = downloads.glob(data['source_package'] + '_*.deb')
    info_deb, = downloads.glob(data['buildinfo_package'] + '_*.deb')
    unpack = work / 'source-deb'; info = work / 'buildinfo'
    run(['dpkg-deb', '-x', source_deb, unpack]); run(['dpkg-deb', '-x', info_deb, info])
    tarball, = (unpack / 'usr/src').glob('linux-source-*.tar.*')
    run(['tar', '-xf', tarball, '-C', work])
    source = work / ('linux-source-' + data['kernel'])
    output = work / 'output'; output.mkdir()
    official = info / 'usr/lib/linux' / (data['kernel'] + '-' + data['abi'] + '-generic')
    original_config = (official / 'config').read_text()
    shutil.copy2(official / 'config', output / '.config')
    (source / 'debian').mkdir(exist_ok=True)
    for name in ['canonical-certs.pem', 'canonical-revoked-certs.pem']:
        shutil.copy2(official / name, source / 'debian' / name)
    pem = os.environ['MODULE_CERT_PEM'].strip() + '\n'
    if 'PRIVATE KEY' in pem or not pem.startswith('-----BEGIN CERTIFICATE-----'):
        raise ValueError('PUBLIC certificate required')
    cert = source / 'certs/sl7-module-cert.pem'; cert.write_text(pem)
    cert_der = work / 'module-cert.der'
    run(['openssl', 'x509', '-in', cert, '-outform', 'DER', '-out', cert_der])
    data['module_cert_der_sha256'] = sha256(cert_der)
    apply_patches(source, logs / 'patches.log')
    config = source / 'scripts/config'
    run([config, '--file', output / '.config', '--module', 'SPI_HID',
         '--set-str', 'MODULE_SIG_KEY', 'certs/sl7-module-cert.pem',
         '--disable', 'LOCALVERSION_AUTO', '--set-str', 'LOCALVERSION', '',
         '--set-str', 'BUILD_SALT', ''])
    gcc = re.search(r'CONFIG_GCC_VERSION=(\d+)', original_config)
    rust = re.search(r'CONFIG_RUSTC_VERSION_TEXT="rustc (\d+\.\d+)', original_config)
    if not gcc or not rust:
        raise RuntimeError('Ubuntu compiler metadata changed; review toolchain selection')
    gcc_major = int(gcc.group(1)) // 10000
    rustc = 'rustc-' + rust.group(1)
    run(['apt-get', 'install', '-y', '--no-install-recommends', f'gcc-{gcc_major}', f'g++-{gcc_major}',
         rustc, 'rust-' + rust.group(1) + '-src', 'bindgen'], env=env)
    make = ['make', '-C', source, 'O=' + str(output),
            'LOCALVERSION=-' + data['abi'] + '-sl7.' + data['release'].split('-sl7.')[1],
            f'CC=gcc-{gcc_major}', f'HOSTCC=gcc-{gcc_major}', f'HOSTCXX=g++-{gcc_major}',
            'RUSTC=' + rustc, 'BINDGEN=bindgen']
    run(make + ['rustavailable'])
    run(make + ['olddefconfig'])
    with (logs / 'config.diff').open('w') as f:
        subprocess.run(['diff', '-u', official / 'config', output / '.config'], stdout=f, check=False)
    for setting in ['CONFIG_SPI_HID=m', 'CONFIG_MODULE_SIG=y', 'CONFIG_SECURITY_LOCKDOWN_LSM=y', 'CONFIG_RUST=y']:
        if setting not in (output / '.config').read_text().splitlines():
            raise RuntimeError('Required setting lost: ' + setting)
    observed = subprocess.check_output([str(x) for x in make + ['-s', 'kernelrelease']], text=True).strip()
    if observed != data['release']:
        raise RuntimeError(f'Unexpected kernel release {observed}')
    with (logs / 'build.log').open('w') as log:
        run(make + ['-j' + str(min(os.cpu_count() or 2, 4)), 'Image', 'modules', 'vmlinuz.efi',
                    'qcom/x1e80100-microsoft-romulus13.dtb'], stdout=log, stderr=subprocess.STDOUT)
    bundle = work / ('sl7-' + data['release'] + '-unsigned'); bundle.mkdir()
    stage = bundle / 'root'; stage.mkdir()
    with (logs / 'modules-install.log').open('w') as log:
        run(make + ['-j4', 'modules_install', 'INSTALL_MOD_PATH=' + str(stage), 'INSTALL_MOD_STRIP=1',
                    'CONFIG_MODULE_SIG_ALL=', 'CONFIG_MODULE_COMPRESS_ALL=', 'DEPMOD=/bin/true'],
            stdout=log, stderr=subprocess.STDOUT)
    modules = stage / 'lib/modules' / data['release']
    for name in ['build', 'source']:
        p = modules / name
        if p.is_symlink():
            p.unlink()
    module_paths = sorted(modules.rglob('*.ko'))
    if not module_paths or list(modules.rglob('*.ko.zst')):
        raise RuntimeError('Expected complete uncompressed unsigned module staging')
    for p in module_paths:
        if p.read_bytes().endswith(b'~Module signature appended~\n'):
            raise RuntimeError('Unexpected signed module in unsigned bundle')
    run(['depmod', '-b', stage, data['release']])
    required = ['ath12k', 'spi-hid', 'spi-geni-qcom', 'gpi', 'surface_aggregator']
    for name in required:
        if not list(modules.rglob(name + '.ko')):
            raise RuntimeError('Missing hardware module: ' + name)
    boot = bundle / 'boot-inputs'; boot.mkdir()
    for src, name in [(output / 'arch/arm64/boot/vmlinuz.efi', 'inner-unsigned.efi'),
                      (output / 'arch/arm64/boot/dts/qcom/x1e80100-microsoft-romulus13.dtb', 'romulus13.dtb'),
                      (output / '.config', 'config'), (output / 'System.map', 'System.map'),
                      (output / 'Module.symvers', 'Module.symvers'), (cert, 'module-cert.pem')]:
        shutil.copy2(src, boot / name)
    # Ship the exact public Stubble inputs; no firmware or private keys.
    stubble_deb = work / 'stubble-deb'; stubble_deb.mkdir()
    run(['apt-get', 'download', 'stubble'], cwd=stubble_deb)
    deb, = stubble_deb.glob('*.deb')
    run(['dpkg-deb', '-x', deb, bundle / 'stubble'])
    shutil.copytree(ROOT / 'ci', bundle / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(output / 'scripts/sign-file', bundle / 'tools/sign-file')
    data.update(module_count=len(module_paths), signed=False, hardware_tested=False,
                patch_sha256={p.name: sha256(p) for p in patches()},
                stubble_deb_sha256=sha256(deb),
                toolchain=subprocess.check_output(['dpkg-query', '-W', '-f=${Package}=${Version}\n'], text=True))
    (bundle / 'BUILD.json').write_text(json.dumps(data, indent=2) + '\n')
    shutil.copytree(logs, bundle / 'logs')
    inventory = [{'path': str(p.relative_to(bundle)), 'sha256': sha256(p)}
                 for p in sorted(bundle.rglob('*')) if p.is_file()]
    (bundle / 'FILES.json').write_text(json.dumps(inventory, indent=2) + '\n')
    verify_files(bundle)
    archive = dist / (bundle.name + '.tar.zst')
    run(['tar', '-I', 'zstd -T2 -6', '-cf', archive, '-C', work, bundle.name])
    run(['zstd', '-t', archive])
    shutil.copy2(bundle / 'BUILD.json', dist / 'BUILD.json')
    for p in downloads.glob('*.deb'):
        shutil.copy2(p, dist / p.name)
    (dist / 'SHA256SUMS').write_text(''.join(sha256(p) + '  ' + p.name + '\n' for p in sorted(dist.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))
    print('Unsigned bundle:', archive, flush=True)


if __name__ == '__main__':
    main()
