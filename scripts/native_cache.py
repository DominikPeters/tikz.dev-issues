#!/usr/bin/env python3
"""Reuse complete compiled inputs for HTML-only updates of a manual."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))
from convert_illustrations import Cache

# These files are consumed only while producing the final site. Mixed Python
# converters, TeX helpers, capture/conversion tools and build scripts stay keyed.
FRONTEND = {
    'shared/style.css', 'shared/pgfmanual.js', 'shared/navbar.py', 'shared/docsearch.py',
    'shared/assets.py', 'shared/pgf_contrib_site.py', 'shared/lwarp_html.py',
    'shared/check_manual_site.py', 'shared/texhtml/site.py',
}
EXCLUDED = {'build', '__pycache__', '.git', 'README.md'}


def lock(package):
    return dict(line.split('=', 1) for line in (ROOT / package / 'upstream.lock').read_text().splitlines()
                if '=' in line and not line.startswith('#'))


def toolchain():
    """Inspect the running tools, not a mutable Docker tag or CI run number."""
    result = {}
    commands = [['lualatex', '--version'],
                ['mutool', '-v'], ['gs', '--version'], ['pdfcrop', '--version'],
                ['pdftex', '--version'], ['pdftocairo', '-v'], ['svgo', '--version'],
                ['pngquant', '--version'], ['rsvg-convert', '--version'],
                ['gnuplot', '--version'], ['convert', '-version']]
    for command in commands:
        process = subprocess.run(command, capture_output=True, text=True, check=True, timeout=90)
        result[command[0]] = process.stdout + process.stderr
    texmfroot = subprocess.check_output(['kpsewhich', '-var-value=TEXMFROOT'], text=True).strip()
    database = Path(texmfroot) / 'tlpkg/texlive.tlpdb'
    result['texlive_packages'] = hashlib.sha256(database.read_bytes()).hexdigest()
    for variable in ['TEXMFHOME', 'TEXMFLOCAL', 'TEXMFCONFIG', 'TEXMFSYSCONFIG']:
        value = subprocess.check_output(['kpsewhich', '-var-value=' + variable], text=True).strip()
        if not value:
            result[variable] = None
            continue
        path = Path(value)
        result[variable] = {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(path.rglob('*')) if p.is_file()} if path.is_dir() else {}
    # System fonts can be used by fontspec independently of TeX Live packages.
    font_dir = Path('/usr/share/fonts')
    result['system_fonts'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(font_dir.rglob('*'))
                              if p.is_file() and p.suffix.lower() in ('.ttf', '.otf', '.ttc')}
    import importlib.metadata
    result['python'] = {name: importlib.metadata.version(name) for name in ['pypdf', 'numpy', 'Pillow']}
    return result


def key(package):
    if os.environ.get('TEXINPUTS') or os.environ.get('LUAINPUTS'):
        raise ValueError('custom TeX search paths require a full build')
    values = lock(package)
    upstream = ROOT / '.upstream' / package
    if values.get('source') == 'archives':
        from archive_upstream import validate_snapshot
        validate_snapshot(package, upstream)
        revision = (upstream / '.source-ref').read_text().strip()
    else:
        revision = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
        # Python converters read the checkout directly; lwarp exports HEAD.
        if (ROOT / package / 'convert.py').exists() and subprocess.check_output(
                ['git', '-C', str(upstream), 'status', '--porcelain', '--untracked-files=all'], text=True).strip():
            raise ValueError('modified upstream checkout requires a full build')
    files = {}
    from dependencies import uses
    used = uses(package, ROOT)
    for directory in [ROOT / package, ROOT / 'shared']:
        for path in sorted(directory.rglob('*')):
            relative = path.relative_to(ROOT).as_posix()
            if (not path.is_file() or EXCLUDED.intersection(path.relative_to(directory).parts)
                    or relative in FRONTEND or path.name == 'postprocessing.py'):
                continue
            # shared Python modules that this manual does not use
            if directory.name == 'shared' and path.suffix == '.py' and relative not in used:
                continue
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ['prepare.py', 'illustration_audit.py', 'native_cache.py', 'build.sh']:
        path = ROOT / 'scripts' / name
        files['scripts/' + name] = hashlib.sha256(path.read_bytes()).hexdigest()
    environment = {name: os.environ.get(name) for name in
                   ['TEXINPUTS', 'LUAINPUTS', 'TEXMFHOME', 'TEXMFVAR', 'LANG', 'LC_ALL',
                    'TIKZ_RENDER_CACHE', 'TIKZ_RENDER_CACHE_MIN_SECONDS', 'SOURCE_DATE_EPOCH', 'FORCE_SOURCE_DATE']}
    # Without a reproducible epoch, \today is an input too. A daily miss is
    # preferable to silently retaining yesterday's title-page date.
    if not environment['SOURCE_DATE_EPOCH'] or environment['FORCE_SOURCE_DATE'] != '1':
        environment['date'] = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    data = {'version': 1, 'package': package, 'upstream': revision, 'files': files,
            'tools': toolchain(), 'environment': environment}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def source_epoch(package):
    values = lock(package)
    if values.get('source') != 'archives':
        return subprocess.check_output(['git', '-C', str(ROOT / '.upstream' / package),
                                        'show', '-s', '--format=%ct', 'HEAD'], text=True).strip()
    import re
    version = json.loads((ROOT / package / values['manifest']).read_text())['version']
    date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", version)
    if date is None:
        raise ValueError('Archive manifest needs a release date for reproducible builds')
    return str(int(datetime.datetime.fromisoformat(date[1]).replace(tzinfo=datetime.timezone.utc).timestamp()))


def locations(package):
    if (ROOT / package / 'convert.py').exists():
        return {'tex': ROOT / package / 'build/tex', 'images': ROOT / package / 'build/images'}
    return {'source': ROOT / 'build' / package / 'src'}


def cache(package):
    base = Path(os.environ.get('TIKZ_COMPILED_CACHE', ROOT / 'build/compiled-cache'))
    return Cache(base / package, ('.tar',))


def save(package, identity):
    store = cache(package)
    if store.valid(identity):
        return
    with tempfile.TemporaryDirectory() as tmp:
        stem = Path(tmp) / 'snapshot'
        with tarfile.open(str(stem) + '.tar', 'w') as archive:
            for name, path in locations(package).items():
                if not path.is_dir():
                    raise ValueError('Missing compiled build input: ' + str(path))
                def include(info):
                    return None if {'__pycache__', '.git', 'processed'}.intersection(Path(info.name).parts) else info
                archive.add(path, arcname=name, filter=include)
        store.store(identity, stem)
    # Each package keeps the current and previous complete native build, rather
    # than uploading an ever-growing history with every Actions cache snapshot.
    entries = sorted(store.root.glob('objects/*/*'), key=lambda p: p.stat().st_mtime, reverse=True)
    previous = [p.name for p in entries if p.name != identity]
    keep = {identity, *previous[:1]}
    for directory in entries:
        if directory.name not in keep:
            with store.lock(directory.name):
                shutil.rmtree(directory, ignore_errors=True)


def restore(package, identity):
    store = cache(package)
    if not store.valid(identity):
        return False
    targets = locations(package)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        store.restore(identity, tmp, 'snapshot')
        with tarfile.open(tmp / 'snapshot.tar') as archive:
            archive.extractall(tmp / 'unpacked', filter='data')
        if not all((tmp / 'unpacked' / name).is_dir() for name in targets):
            return False
        # Validate/extract everything before replacing any current build tree.
        for name, destination in targets.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged = Path(tempfile.mkdtemp(dir=destination.parent))
            shutil.copytree(tmp / 'unpacked' / name, staged / 'result')
            previous = staged / 'previous'
            if destination.exists():
                destination.rename(previous)
            try:
                (staged / 'result').rename(destination)
            except BaseException:
                if previous.exists():
                    previous.rename(destination)
                raise
            finally:
                shutil.rmtree(staged)
    return True


def html(package):
    values = lock(package)
    if (ROOT / package / 'convert.py').exists():
        environment = dict(os.environ, UPSTREAM=str(ROOT / '.upstream' / package))
        subprocess.run([str(ROOT / package / 'build.sh'), 'html'], env=environment, check=True)
    else:
        from prepare import overlay
        source = ROOT / 'build' / package / 'src'
        overlay(package, str(source), values['docdir'])
        docdir = source / values['docdir']
        shutil.rmtree(docdir / 'processed', ignore_errors=True)
        subprocess.run([sys.executable, 'postprocessing.py'], cwd=docdir, check=True)
        if package == 'pgfplots':
            subprocess.run(['svgo', '-f', 'processed/pgfplots-images'], cwd=docdir, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['key', 'restore', 'save', 'html', 'epoch'])
    parser.add_argument('package')
    parser.add_argument('identity', nargs='?')
    args = parser.parse_args()
    if args.action == 'epoch':
        print(source_epoch(args.package))
    elif args.action == 'key':
        try:
            print(key(args.package))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print('Compiled cache unavailable: ' + str(error), file=sys.stderr)
            return 1
    elif args.action == 'restore':
        try:
            restored = args.identity and restore(args.package, args.identity)
        except (OSError, ValueError, RuntimeError, tarfile.TarError) as error:
            print('Compiled cache rejected: ' + str(error), file=sys.stderr)
            return 1
        if not restored:
            return 1
        print(args.package + ': reusing compiled output; LaTeX and image conversion skipped')
    elif args.action == 'save':
        save(args.package, args.identity)
    else:
        html(args.package)
    return 0


if __name__ == '__main__':
    sys.exit(main())
