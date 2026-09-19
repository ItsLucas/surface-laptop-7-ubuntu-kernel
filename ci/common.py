"""Shared input validation for the kernel builder. No private keys belong in CI."""
import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(argv, **kw):
    return subprocess.run([str(x) for x in argv], check=True, **kw)


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def series_names(root, filename, optional=False):
    path = root / 'patches' / filename
    if optional and not path.exists():
        return []
    names = [s.strip() for s in path.read_text().splitlines()
             if s.strip() and not s.lstrip().startswith('#')]
    if (not names and not optional) or len(set(names)) != len(names):
        raise ValueError('Empty/duplicate patch series')
    if any(not re.fullmatch(r'[a-zA-Z0-9_.-]+\.patch', name) for name in names):
        raise ValueError('Unsafe patch name')
    return names


def patches(root=ROOT, kernel=None):
    series = None
    if kernel is not None:
        if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', kernel):
            raise ValueError('Invalid kernel version for patch selection')
        series = '.'.join(kernel.split('.')[:2])
    names = (series_names(root, 'series') +
             series_names(root, 'series-if-needed', optional=True))
    if len(set(names)) != len(names):
        raise ValueError('Duplicate patch across series manifests')
    for name in names:
        variant = root / 'patches/variants' / series / name if series else None
        yield variant if variant is not None and variant.is_file() else root / 'patches' / name


def recipe_hash(cert_pem, root=ROOT):
    h = hashlib.sha256()
    inputs = [root / 'patches/series', root / 'patches/series-if-needed',
              *patches(root), *sorted((root / 'patches/variants').rglob('*.patch')),
              *sorted((root / 'ci').rglob('*')),
              *sorted((root / 'drivers').rglob('*')),
              *sorted((root / 'tests').rglob('*')),
              *sorted((root / '.github/workflows').glob('*.yml'))]
    for p in inputs:
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
            h.update(str(p.relative_to(root)).encode() + b'\0' + p.read_bytes() + b'\0')
    h.update(cert_pem.encode())
    return h.hexdigest()


def image_release(name):
    match = re.fullmatch(r'linux-image-(\d+\.\d+\.\d+)-(\d+)-generic', name)
    if not match:
        raise ValueError(f'Unexpected Ubuntu generic kernel package: {name}')
    return match.group(1), match.group(2)


def release_name(kernel, abi, run_number, attempt):
    for n in (run_number, attempt):
        if not re.fullmatch(r'[1-9][0-9]*', str(n)):
            raise ValueError('Run number/attempt must be positive integers')
    release = f'{kernel}-{abi}-sl7.{run_number}.{attempt}'
    if len(release) > 63:
        raise ValueError('Kernel release exceeds UTS length')
    return release


def apply_patches(source, log, root=ROOT, kernel=None):
    reviewed_optional = set(series_names(root, 'series-if-needed', optional=True))
    results = []
    with Path(log).open('w') as out:
        for patch in patches(root, kernel=kernel):
            rel = str(patch.relative_to(root / 'patches'))
            out.write(f'Checking {rel}\n'); out.flush()
            args = ['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', patch]
            probe = subprocess.run(args + ['--dry-run'], cwd=source,
                                   stdout=out, stderr=subprocess.STDOUT)
            if probe.returncode:
                if patch.name in reviewed_optional:
                    # Recognize all postimage hunks without changing any source.
                    # Unknown/partially applied upstream changes still fail closed.
                    reverse = ['patch', '--batch', '--force', '--reverse', '--dry-run',
                               '--fuzz=0', '-p1', '-i', patch]
                    check = subprocess.run(reverse, cwd=source,
                                           stdout=out, stderr=subprocess.STDOUT)
                    if check.returncode == 0:
                        out.write(f'Not needed: {rel} (all postimage hunks verified)\n')
                        out.flush()
                        results.append({'path': rel, 'status': 'not-needed'})
                        continue
                raise subprocess.CalledProcessError(probe.returncode, args + ['--dry-run'])
            run(args, cwd=source, stdout=out, stderr=subprocess.STDOUT)
            results.append({'path': rel, 'status': 'applied'})
    return results


def verify_files(directory):
    """Verify a manifest without allowing symlinks or paths outside the bundle."""
    import json
    directory = Path(directory).resolve()
    records = json.loads((directory / 'FILES.json').read_text())
    seen = set()
    for item in records:
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts or str(rel) in seen:
            raise ValueError('Unsafe or duplicate manifest path')
        seen.add(str(rel))
        p = directory / rel
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(directory):
            raise ValueError(f'Unsafe/missing file: {rel}')
        if sha256(p) != item['sha256']:
            raise ValueError(f'Hash mismatch: {rel}')
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
    if actual != seen | {'FILES.json'} or any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('Unexpected files or symlinks in bundle')
    return records
