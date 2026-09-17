#!/usr/bin/env python3
"""Resolve Ubuntu 26.10's signed APT candidate and skip an already built recipe."""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
from common import image_release, recipe_hash, release_name


def resolve(cache):
    meta = cache['linux-image-generic'].candidate
    names = [d.name for group in meta.dependencies for d in group.or_dependencies
             if re.fullmatch(r'linux-image-\d+\.\d+\.\d+-\d+-generic', d.name)]
    if len(names) != 1:
        raise RuntimeError('Generic kernel dependency layout changed; review required')
    image = names[0]
    kernel, abi = image_release(image)
    info = cache[f'linux-buildinfo-{kernel}-{abi}-generic'].candidate
    source = cache[f'linux-source-{kernel}'].candidate
    if info.source_name != 'linux' or source.source_name != 'linux' or info.version != source.version:
        raise RuntimeError('Source/config publication is incomplete or source family changed')
    inputs = {}
    for name, version in [(image, cache[image].candidate), (info.package.name, info), (source.package.name, source)]:
        inputs[name] = {'version': version.version, 'uri': version.uri,
                        'source': version.source_name, 'source_version': version.source_version}
    return {'suite': 'stonking', 'architecture': 'arm64', 'flavour': 'generic',
            'ubuntu_version': source.version, 'kernel': kernel, 'abi': abi,
            'source_package': source.package.name, 'buildinfo_package': info.package.name,
            'image_package': image, 'inputs': inputs}


def main():
    import apt
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=Path('work/input.json'))
    ap.add_argument('--offline', action='store_true', help='Inspect existing APT cache only; no GitHub lookup')
    args = ap.parse_args()
    pem = os.environ.get('MODULE_CERT_PEM', '').strip() + '\n'
    if 'PRIVATE KEY' in pem or not pem.startswith('-----BEGIN CERTIFICATE-----'):
        raise SystemExit('Set repository variable MODULE_CERT_PEM to the PUBLIC module-signing certificate')
    data = resolve(apt.Cache())
    fingerprint = recipe_hash(pem)
    version_tag = re.sub(r'[^a-zA-Z0-9._-]', '-', data['ubuntu_version'])
    tag = f'ubuntu-{version_tag}-p{fingerprint[:16]}'
    exists = False
    if not args.offline:
        repository = os.environ['GITHUB_REPOSITORY']
        request = urllib.request.Request(f'https://api.github.com/repos/{repository}/releases/tags/{tag}',
                  headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                release = json.load(response)
            exists = not release['draft'] and any(a['name'].endswith('-unsigned.tar.zst') for a in release['assets'])
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    number = os.environ.get('GITHUB_RUN_NUMBER', '1')
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    # Every actual run gets a unique release/tag; the recipe key is recorded in release names.
    should_build = not exists or os.environ.get('FORCE_BUILD') == 'true'
    data.update(recipe_sha256=fingerprint, cache_tag=tag,
                release_tag=(tag + f'-r{number}.{attempt}') if exists else tag,
                release=release_name(data['kernel'], data['abi'], number, attempt),
                package_version=data['ubuntu_version'] + f'+sl7.{number}.{attempt}',
                source_commit=os.environ.get('GITHUB_SHA', 'local-validation'),
                should_build=should_build)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            for key, value in {'build': str(should_build).lower(), 'tag': data['release_tag'], 'release': data['release']}.items():
                out.write(f'{key}={value}\n')
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
