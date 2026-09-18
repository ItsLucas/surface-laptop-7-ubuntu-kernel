#!/usr/bin/env python3
"""Pull completed native-package Releases; never promote candidates to stable."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request
from publish import publish

API = 'https://api.github.com/repos/ItsLucas/surface-laptop-7-ubuntu-kernel/releases?per_page=30'
PREFIX = 'https://github.com/ItsLucas/surface-laptop-7-ubuntu-kernel/releases/download/'


def read(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'sl7-apt-sync'})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def asset_download(asset, directory):
    name = asset['name']
    if Path(name).name != name or not asset['browser_download_url'].startswith(PREFIX):
        raise ValueError('Unsafe GitHub asset')
    path = directory / name
    request = urllib.request.Request(asset['browser_download_url'], headers={'User-Agent': 'sl7-apt-sync'})
    h = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=90) as response, path.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            h.update(chunk)
            output.write(chunk)
    if asset.get('digest') != 'sha256:' + h.hexdigest():
        raise ValueError('GitHub asset digest mismatch')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/srv/sl7-apt'))
    parser.add_argument('--signing-key', required=True)
    args = parser.parse_args()
    state = args.root / 'synced.json'
    done = json.loads(state.read_text()) if state.exists() else []
    releases = json.loads(read(API))
    # Oldest first. Package versions, rather than publication time, select
    # the APT candidate, and immutable filenames prevent silent replacement.
    for release in reversed(releases):
        if release['draft'] or release['tag_name'] in done:
            continue
        assets = {a['name']: a for a in release['assets']}
        if 'SIGNING.json' not in assets:
            continue
        with tempfile.TemporaryDirectory(prefix='incoming-', dir=args.root) as temporary:
            directory = Path(temporary)
            report = json.loads(asset_download(assets['SIGNING.json'], directory).read_text())
            if report.get('installation') != 'ubuntu-kernel-hooks-dracut-grub':
                continue
            for name in report['packages']:
                asset_download(assets[name], directory)
            publish(args.root, 'candidate', args.signing_key, directory)
        done.append(release['tag_name'])
        temporary_state = state.with_suffix('.tmp')
        temporary_state.write_text(json.dumps(done) + '\n')
        temporary_state.replace(state)
    publish(args.root, 'candidate', args.signing_key)


if __name__ == '__main__':
    main()
