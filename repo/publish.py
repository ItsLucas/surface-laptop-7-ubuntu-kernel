#!/usr/bin/env python3
"""Publish immutable debs and switch a signed, by-hash APT snapshot atomically."""
import argparse
import datetime
import email.utils
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_packages(directory):
    report = json.loads((directory / 'SIGNING.json').read_text())
    if report.get('installation') != 'ubuntu-kernel-hooks-dracut-grub' or not report.get('signed'):
        raise ValueError('Only signed packages with native installation hooks can be published')
    release = report['release']
    if not re.fullmatch(r'\d+\.\d+\.\d+-\d+-sl7\.\d+\.\d+', release):
        raise ValueError('Invalid release')
    expected_names = {'linux-image-' + release: 'arm64', 'linux-sl7': 'arm64', 'linux-sl7-support': 'all'}
    found = {}
    versions = set()
    packages = []
    if len(report['packages']) != 3:
        raise ValueError('Expected image, support and metapackage')
    for filename, sha in report['packages'].items():
        if not re.fullmatch(r'[a-zA-Z0-9.+~_-]+\.deb', filename):
            raise ValueError('Unsafe package filename')
        path = directory / filename
        if path.is_symlink() or digest(path) != sha:
            raise ValueError('Package hash mismatch: ' + filename)
        fields = subprocess.check_output(['dpkg-deb', '-f', path, 'Package', 'Version', 'Architecture'], text=True)
        metadata = dict(line.split(': ', 1) for line in fields.splitlines())
        name, arch, version = metadata['Package'], metadata['Architecture'], metadata['Version']
        if name in found or expected_names.get(name) != arch or filename != f'{name}_{version}_{arch}.deb':
            raise ValueError('Unexpected package identity')
        found[name] = path
        versions.add(version)
        packages.append(path)
    if set(found) != set(expected_names) or len(versions) != 1:
        raise ValueError('Incomplete or mixed package set')
    image = found['linux-image-' + release]
    if report['package'] != image.name or report['sha256'] != digest(image):
        raise ValueError('Image report mismatch')
    return packages, report


def publish(root, component, signing_key, incoming=None):
    public = root / 'public'
    public.mkdir(parents=True, exist_ok=True)
    with (root / 'publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for channel in ['candidate', 'stable']:
            (public / 'pool' / channel).mkdir(parents=True, exist_ok=True)
        if incoming:
            packages, report = checked_packages(incoming)
            # Preflight the whole import before changing the pool.
            for package in packages:
                dest = public / 'pool' / component / package.name
                if dest.exists() and digest(dest) != digest(package):
                    raise ValueError('Refusing to replace immutable package: ' + package.name)
            for package in packages:
                dest = public / 'pool' / component / package.name
                if not dest.exists():
                    temporary = dest.with_suffix('.tmp')
                    shutil.copyfile(package, temporary)
                    temporary.chmod(0o644)
                    temporary.replace(dest)

        snapshots = root / 'snapshots'
        snapshots.mkdir(exist_ok=True)
        generation = Path(tempfile.mkdtemp(prefix='snapshot-', dir=snapshots))
        generation.chmod(0o755)
        suite = generation / 'dists/stonking'
        records = []
        for channel in ['candidate', 'stable']:
            relative = Path(channel) / 'binary-arm64'
            target = suite / relative
            target.mkdir(parents=True)
            by_hash = target / 'by-hash/SHA256'
            previous = public / 'dists/stonking' / relative / 'by-hash/SHA256'
            if previous.is_dir():
                shutil.copytree(previous, by_hash, copy_function=os.link)
            else:
                by_hash.mkdir(parents=True)
            index = subprocess.check_output(['dpkg-scanpackages', '--multiversion',
                                              'pool/' + channel, '/dev/null'], cwd=public)
            (target / 'Packages').write_bytes(index)
            (target / 'Packages.gz').write_bytes(gzip.compress(index, mtime=0))
            for name in ['Packages', 'Packages.gz']:
                path = target / name
                sha = digest(path)
                link = by_hash / sha
                if not link.exists():
                    os.link(path, link)
                records.append(f' {sha} {path.stat().st_size} {relative / name}\n')
        now = datetime.datetime.now(datetime.timezone.utc)
        (suite / 'Release').write_text(
            'Origin: SL7\nLabel: Surface Laptop 7\nSuite: stonking\nCodename: stonking\n'
            f'Date: {email.utils.format_datetime(now, usegmt=True)}\n'
            f'Valid-Until: {email.utils.format_datetime(now + datetime.timedelta(days=14), usegmt=True)}\n'
            'Architectures: arm64\nComponents: candidate stable\nAcquire-By-Hash: yes\n'
            'Description: Ubuntu 26.10 Surface Laptop 7 13.8-inch kernels\nSHA256:\n' + ''.join(records))
        gpg = ['gpg', '--homedir', str(root / 'gnupg'), '--batch', '--yes', '--local-user', signing_key]
        subprocess.run(gpg + ['--clearsign', '--output', suite / 'InRelease', suite / 'Release'], check=True)
        subprocess.run(gpg + ['--armor', '--detach-sign', '--output', suite / 'Release.gpg', suite / 'Release'], check=True)
        replacement = public / '.dists-new'
        replacement.unlink(missing_ok=True)  # Recover a crash before the previous rename.
        replacement.symlink_to(os.path.relpath(generation / 'dists', public))
        replacement.replace(public / 'dists')
        if incoming:
            reports = public / 'reports' / component
            reports.mkdir(parents=True, exist_ok=True)
            (reports / (report['release'] + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        # Old by-hash files are linked into every new generation, so clients
        # holding a previous InRelease can finish even across publication.
        old = sorted(snapshots.iterdir(), key=lambda p: p.stat().st_mtime)
        for path in old[:-3]:
            if path != generation:
                shutil.rmtree(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/srv/sl7-apt'))
    parser.add_argument('--component', choices=['candidate', 'stable'], default='candidate')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--signing-key', required=True)
    args = parser.parse_args()
    publish(args.root, args.component, args.signing_key, args.input)


if __name__ == '__main__':
    main()
