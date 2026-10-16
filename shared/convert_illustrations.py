#!/usr/bin/env python3
"""Convert lwarp illustrations in batches, caching complete rendered results."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import pypdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import _base as pdf_objects

from crop_latex_image import crop


SUFFIXES = ('.svg', '.png')
MANIFEST_NAME = re.compile(r'[A-Za-z0-9_-]+')
RENDER_CACHE_KEY = re.compile(r'[a-f0-9]{64}-[0-9]+')
# pypdf defaults to eight significant digits when writing resource matrices.
# Preserve the input PDF's double precision: rounding can change antialiasing
# and, consequently, the palette selected by pngquant.
pdf_objects.FLOAT_WRITE_PRECISION = 16


def run(command, cwd=None):
    # pngquant can itself use multiple cores; keep the worker limit meaningful.
    env = dict(os.environ, OMP_NUM_THREADS='1')
    result = subprocess.run(command, capture_output=True, text=True, env=env, cwd=cwd)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(map(str, command))}\n"
                           f"{result.stdout}{result.stderr}")
    return result.stdout + result.stderr


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_manifest(path, allow_missing_end=False):
    entries = {}
    ended = False
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        if ended:
            raise ValueError('Image manifest has data after its end marker')
        if line == '|end|end|end|':
            ended = True
            continue
        match = re.fullmatch(r'\|([1-9][0-9]*)\|(true|false)\|([A-Za-z0-9_-]+)\|', line)
        if not match:
            raise ValueError(f'Invalid or unresolved image manifest entry: {line}')
        page, _, name = match.groups()
        # Hashed images can occur on several pages; render the first occurrence.
        if name in entries and match[2] != 'true' and entries[name] != int(page):
            raise ValueError(f'Conflicting pages for image {name}')
        entries.setdefault(name, int(page))
    if not ended and not allow_missing_end:
        raise ValueError('Image manifest has no end marker; LaTeX may have aborted')
    if not entries:
        raise ValueError('Image manifest is empty')
    return entries


def conversion_signature(magick):
    commands = [('pdftocairo', '-v'), ('pdfseparate', '-v'), ('pdfcrop', '--version'), ('gs', '--version'),
                ('pdftex', '--version'), ('pngquant', '--version')]
    if magick:
        commands.append(('convert', '-version'))
    settings = {'pypdf': pypdf.__version__, 'magick': magick,
                'converter': file_digest(Path(__file__)),
                'crop': file_digest(Path(__file__).with_name('crop_latex_image.py')),
                'tools': [run(command) for command in commands]}
    return digest(json.dumps(settings, sort_keys=True).encode())


def page_bytes(page):
    writer = PdfWriter()
    writer.add_page(page)
    # Document timestamps/IDs are not drawing content. Resource objects,
    # including font programs and images, remain part of the fingerprint.
    writer.metadata = None
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def read_render_cache_used(source, manifest_entries):
    """Read and validate the optional per-document original-page cache map."""
    path = source.with_suffix('.render-cache-used.jsonl')
    if not path.exists():
        return None, {}, {}
    contents = path.read_bytes()
    used = {}

    def unique_object_fields(pairs):
        record = {}
        for name, value in pairs:
            if name in record:
                raise ValueError(f'Duplicate JSON field: {name}')
            record[name] = value
        return record

    for line_number, line in enumerate(contents.decode('utf-8').splitlines(), 1):
        if not line:
            raise ValueError(f'Invalid render-cache record on line {line_number}: empty line')
        try:
            record = json.loads(line, object_pairs_hook=unique_object_fields)
        except ValueError as error:
            raise ValueError(f'Invalid render-cache record on line {line_number}: {error}') from error
        if (not isinstance(record, dict) or set(record) != {'name', 'key'} or
                not isinstance(record['name'], str) or not isinstance(record['key'], str) or
                MANIFEST_NAME.fullmatch(record['name']) is None or
                RENDER_CACHE_KEY.fullmatch(record['key']) is None):
            raise ValueError(f'Invalid render-cache record on line {line_number}')
        name, key = record['name'], record['key']
        if name not in manifest_entries:
            raise ValueError(f'Render-cache map contains unknown image name: {name}')
        if name in used and used[name] != key:
            raise ValueError(f'Conflicting render-cache keys for image {name}')
        used[name] = key

    paths = {}
    file_digests = {}
    for name, key in used.items():
        cached_pdf = source.with_suffix('.render-cache') / f'{key}.pdf'
        if not cached_pdf.is_file():
            raise ValueError(f'Render-cache PDF is missing for image {name}: {cached_pdf}')
        try:
            reader = PdfReader(cached_pdf)
            if len(reader.pages) != 1:
                raise ValueError(f'Render-cache PDF for image {name} must contain exactly one page')
        except (OSError, ValueError) as error:
            if isinstance(error, ValueError) and 'must contain exactly one page' in str(error):
                raise
            raise ValueError(f'Invalid render-cache PDF for image {name}: {cached_pdf}') from error
        paths[name] = cached_pdf
        file_digests[name] = file_digest(cached_pdf)
        del reader
    return contents, used, {'paths': paths, 'digests': file_digests}


class Cache:
    def __init__(self, root, suffixes):
        self.root = root
        self.suffixes = suffixes

    def directory(self, key):
        if re.fullmatch('[0-9a-f]{64}', key) is None:
            raise ValueError('Invalid illustration cache key')
        return self.root / 'objects' / key[:2] / key

    def valid(self, key):
        directory = self.directory(key)
        try:
            metadata = json.loads((directory / 'complete.json').read_text())
            return all((directory / ('image' + suffix)).stat().st_size > 0 and
                       file_digest(directory / ('image' + suffix)) == metadata[suffix]
                       for suffix in self.suffixes)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    @contextmanager
    def lock(self, key):
        locks = self.root / 'locks'
        locks.mkdir(parents=True, exist_ok=True)
        with (locks / key).open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def store(self, key, stem):
        directory = self.directory(key)
        directory.parent.mkdir(parents=True, exist_ok=True)
        with self.lock(key):
            if self.valid(key):
                return
            with tempfile.TemporaryDirectory(dir=directory.parent) as temporary:
                staged = Path(temporary) / 'result'
                staged.mkdir()
                metadata = {}
                for suffix in self.suffixes:
                    source = Path(str(stem) + suffix)
                    if source.stat().st_size == 0:
                        raise RuntimeError(f'Empty converted illustration: {source}')
                    shutil.copyfile(source, staged / ('image' + suffix))
                    metadata[suffix] = file_digest(source)
                (staged / 'complete.json').write_text(json.dumps(metadata))
                if directory.exists():
                    shutil.rmtree(directory)
                staged.rename(directory)

    def restore(self, key, output, name):
        # Lock against repair of a damaged cache entry by another build.
        with self.lock(key):
            if not self.valid(key):
                raise RuntimeError(f'Illustration cache entry disappeared: {key}')
            for suffix in self.suffixes:
                with tempfile.NamedTemporaryFile(dir=output, delete=False) as stream:
                    temporary = Path(stream.name)
                try:
                    shutil.copyfile(self.directory(key) / ('image' + suffix), temporary)
                    temporary.chmod(0o644)
                    temporary.replace(output / (name + suffix))
                finally:
                    temporary.unlink(missing_ok=True)


def ghostscript_wrapper(directory, pages, executable=None):
    """Give pdfcrop independent page bounds without losing batched PDF assembly.

    Ghostscript's font cache can change a glyph's bounds between pages. A
    fresh process per page matches the original single-page crop behavior.
    """
    wrapper = directory / 'gs-per-page.py'
    wrapper.write_text(
        '#!/usr/bin/env python3\n'
        'import subprocess, sys\n'
        f'ghostscript = {str(executable or shutil.which("gs"))!r}\n'
        f'pages = {[str(page) for page in pages]!r}\n'
        'arguments = sys.argv[1:]\n'
        'if "-sDEVICE=bbox" not in arguments:\n'
        '    raise SystemExit(subprocess.run([ghostscript, *arguments]).returncode)\n'
        'for page in pages:\n'
        '    result = subprocess.run([ghostscript, *arguments[:-1], page])\n'
        '    if result.returncode:\n'
        '        raise SystemExit(result.returncode)\n'
    )
    wrapper.chmod(0o755)
    return wrapper


def convert_batch(batch_pdf, items, directory, cache, magick):
    run(['pdfseparate', '-f', '1', '-l', str(len(items)), str(batch_pdf),
         str(directory / 'source-%d.pdf')])
    wrapper = ghostscript_wrapper(directory, [directory / f'source-{n}.pdf'
                                              for n in range(1, len(items) + 1)])
    cropped = directory / 'cropped.pdf'
    messages = run(['pdfcrop', '--gscmd', str(wrapper), '--margins', '1', '--hires',
                    str(batch_pdf), str(cropped)], cwd=directory)
    if len(PdfReader(cropped).pages) != len(items):
        raise RuntimeError('Cropping changed the number of illustration pages')
    blanks = {int(page) for page in re.findall(r'!!!\s+Page (\d+):', messages)}
    # Split once per batch, preserving Poppler's PDF number precision.
    run(['pdfseparate', '-f', '1', '-l', str(len(items)), str(cropped),
         str(directory / '%d.pdf')])
    for number, (_, key) in enumerate(items, 1):
        stem = directory / str(number)
        pdf = stem.with_suffix('.pdf')
        if number in blanks:
            # Preserve the existing minimal canvas for genuinely empty pages.
            fixed = directory / 'blank.pdf'
            if crop(str(pdf), str(fixed), cwd=directory):
                raise RuntimeError('Could not crop an empty illustration')
            fixed.replace(pdf)
        run(['pdftocairo', '-svg', '-noshrink', str(pdf), str(stem) + '.svg'])
        run(['pdftocairo', '-png', '-transp', '-r', '300', '-singlefile', str(pdf), str(stem)])
        run(['pngquant', '--force', '--ext', '.png', '--', str(stem) + '.png'])
        if magick:
            run(['convert', '-density', '300', str(pdf), str(stem) + '.magick.png'])
            run(['pngquant', '--force', '--ext', '.png', '--', str(stem) + '.magick.png'])
        cache.store(key, stem)
    return len(items)


def convert(source, manifest, output, cache_root, jobs=4, batch_size=16, magick=False,
            allow_missing_end=False):
    started = time.monotonic()
    entries = read_manifest(manifest, allow_missing_end)
    used_map_contents, used_map, render_cache = read_render_cache_used(source, entries)
    signature = conversion_signature(magick)
    cache = Cache(cache_root, SUFFIXES + (('.magick.png',) if magick else ()))
    document_fingerprint = file_digest(source) + file_digest(manifest) + signature
    if used_map_contents is not None:
        render_cache_fingerprint = {
            'map': digest(used_map_contents),
            'pdfs': sorted((name, used_map[name], render_cache['digests'][name])
                           for name in used_map),
        }
        document_fingerprint += json.dumps(render_cache_fingerprint, sort_keys=True)
    document_key = digest(document_fingerprint.encode())
    index_file = cache_root / 'documents' / (document_key + '.json')
    try:
        keys = json.loads(index_file.read_text())
        if (not isinstance(keys, dict) or set(keys) != set(entries) or
                any(not isinstance(key, str) or re.fullmatch('[0-9a-f]{64}', key) is None
                    for key in keys.values())):
            keys = {}
    except (OSError, ValueError, TypeError):
        keys = {}
    reader = None
    missing = []
    for name, page_number in entries.items():
        if name not in keys:
            if name in used_map:
                cached_reader = PdfReader(render_cache['paths'][name])
                drawing_page = cached_reader.pages[0]
            else:
                if reader is None:
                    reader = PdfReader(source)
                if page_number > len(reader.pages):
                    raise ValueError(f'Image {name} refers to missing PDF page {page_number}')
                drawing_page = reader.pages[page_number - 1]
            keys[name] = digest(signature.encode() + page_bytes(drawing_page))
            if name in used_map:
                del cached_reader, drawing_page
        if not cache.valid(keys[name]):
            missing.append(name)
    hits = len(entries) - len(missing)
    print(f'Illustrations: {len(entries)} total, {hits} cached, {len(missing)} to convert', flush=True)
    with tempfile.TemporaryDirectory(prefix='illustrations-') as temporary:
        if missing and reader is None:
            reader = PdfReader(source)
        batches = []
        for start in range(0, len(missing), batch_size):
            names = missing[start:start + batch_size]
            directory = Path(temporary) / str(start)
            directory.mkdir()
            batch_pdf = directory / 'input.pdf'
            writer = PdfWriter()
            for name in names:
                if name in used_map:
                    cached_reader = PdfReader(render_cache['paths'][name])
                    writer.add_page(cached_reader.pages[0])
                    del cached_reader
                else:
                    writer.add_page(reader.pages[entries[name] - 1])
            writer.metadata = None
            writer.write(batch_pdf)
            batches.append((batch_pdf, [(name, keys[name]) for name in names], directory))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(convert_batch, pdf, items, directory, cache, magick)
                       for pdf, items, directory in batches]
            completed = 0
            for future in futures:
                completed += future.result()
                print(f'Converted {completed}/{len(missing)} illustrations', flush=True)
    # Only publish outputs after every worker has succeeded. No placeholder SVGs.
    output.mkdir(parents=True, exist_ok=True)
    for name in entries:
        cache.restore(keys[name], output, name)
    index_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=index_file.parent, delete=False) as stream:
        json.dump(keys, stream)
        temporary_index = Path(stream.name)
    temporary_index.replace(index_file)
    elapsed = time.monotonic() - started
    print(f'Illustrations ready: {len(entries)} ({hits} cached) in {elapsed:.1f}s', flush=True)
    return {'total': len(entries), 'cached': hits, 'converted': len(missing), 'seconds': elapsed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cache', type=Path, default=Path(os.environ.get('TIKZ_IMAGE_CACHE', '.illustration-cache')))
    parser.add_argument('--jobs', type=int, default=int(os.environ.get('TIKZ_IMAGE_JOBS', '4')))
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--magick', action='store_true', help='also render PGFplots shader fallbacks')
    parser.add_argument('--allow-missing-end', action='store_true', help='accept PGFplots manifests without an end marker')
    args = parser.parse_args()
    if args.jobs < 1 or args.batch_size < 1:
        parser.error('jobs and batch-size must be positive')
    try:
        convert(args.source, args.manifest, args.output, args.cache, args.jobs,
                args.batch_size, args.magick, args.allow_missing_end)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'Illustration conversion failed: {error}\n')


if __name__ == '__main__':
    main()
