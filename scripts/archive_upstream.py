#!/usr/bin/env python3
"""Fetch checksum-pinned TeX sources from immutable distribution archives.

This supplies packages distributed on CTAN without an upstream Git repository.
Only the files named in the manifest are extracted; all other archive content
is ignored. Downloads are cached by SHA-256 outside prepared build trees.
"""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_lock(package):
    return dict(line.split('=', 1) for line in
                (ROOT / package / 'upstream.lock').read_text().splitlines()
                if '=' in line and not line.startswith('#'))


def manifest(package):
    lock = read_lock(package)
    path = ROOT / package / lock['manifest']
    if sha256(path) != lock['commit']:
        raise ValueError('Source manifest differs from its pinned SHA-256')
    return lock, json.loads(path.read_text())


def checked_target(target):
    path = Path(target)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0].startswith('.'):
        raise ValueError('Unsafe source destination: ' + target)
    return path


def download(archive, cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (archive['sha256'] + '.deb')
    if path.exists():
        if sha256(path) != archive['sha256']:
            raise ValueError('Cached archive checksum mismatch: ' + str(path))
        return path
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with urllib.request.urlopen(archive['url'], timeout=60) as response:
                shutil.copyfileobj(response, stream)
            stream.close()
            if sha256(temporary) != archive['sha256']:
                raise ValueError('Downloaded archive checksum mismatch: ' + archive['url'])
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


def extract_deb(path, files, destination):
    targets = {source.removeprefix('./'): checked_target(target) for source, target in files.items()}
    found = set()
    process = subprocess.Popen(['dpkg-deb', '--fsys-tarfile', str(path)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                name = member.name.removeprefix('./')
                if name not in targets:
                    continue
                if not member.isfile() or name in found:
                    raise ValueError('Unexpected source archive member: ' + name)
                content = archive.extractfile(member).read()
                if name.endswith('.gz') and not str(targets[name]).endswith('.gz'):
                    content = gzip.decompress(content)
                target = destination / targets[name]
                if target.exists():
                    raise ValueError('Duplicate source destination: ' + str(targets[name]))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                found.add(name)
        if process.wait():
            raise ValueError('Could not read distribution archive: ' + str(path))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
    if found != set(targets):
        raise ValueError('Missing source files: ' + ', '.join(sorted(set(targets) - found)))


def validate_snapshot(package, directory):
    lock, data = manifest(package)
    state = json.loads((directory / '.source-files.json').read_text())
    expected = {target for item in data['archives'] for target in item['files'].values()}
    if (directory / '.source-ref').read_text().strip() != lock['commit'] or set(state) != expected:
        raise ValueError('Source snapshot does not match the lock; run scripts/fetch.sh ' + package)
    for name, digest in state.items():
        if sha256(directory / checked_target(name)) != digest:
            raise ValueError('Source snapshot changed: ' + name)
    return state


def fetch(package, requested=None):
    lock, data = manifest(package)
    if requested and requested != lock['commit']:
        raise ValueError('Archive sources use the revision pinned in their manifest')
    directory = ROOT / '.upstream' / package
    if directory.exists():
        if (directory / '.source-ref').read_text().strip() == lock['commit']:
            validate_snapshot(package, directory)
            print(f'{package}: {data["version"]} ({lock["commit"][:12]})')
            return
    directory.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent) as temporary:
        stage = Path(temporary) / 'source'
        stage.mkdir()
        for item in data['archives']:
            archive = download(item, directory.parent / 'archive-cache')
            extract_deb(archive, item['files'], stage)
        files = {str(p.relative_to(stage)): sha256(p) for p in stage.rglob('*') if p.is_file()}
        (stage / '.source-files.json').write_text(json.dumps(files, indent=2) + '\n')
        (stage / '.source-ref').write_text(lock['commit'] + '\n')
        if directory.exists():
            shutil.rmtree(directory)
        stage.rename(directory)
    validate_snapshot(package, directory)
    print(f'{package}: {data["version"]} ({lock["commit"][:12]})')


if __name__ == '__main__':
    fetch(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
