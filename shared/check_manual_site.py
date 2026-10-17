"""Validate files and anchors inside a generated manual, without network access."""
import argparse
from collections import Counter
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup


def check_site(directory):
    root = Path(directory).resolve()
    pages = {p.resolve(): BeautifulSoup(p.read_text(), 'html5lib') for p in root.glob('*.html')}
    if root / 'index.html' not in pages:
        raise ValueError('Manual has no index.html')
    anchors = {p: {tag['id'] for tag in soup.find_all(id=True)} for p, soup in pages.items()}
    errors = []
    counts = Counter(pages=len(pages))
    for page, soup in pages.items():
        counts['examples'] += len(soup.select('.example'))
        counts['images'] += len(soup.find_all('img'))
        counts['entries'] += len(soup.select('.manualentry'))
        ids = [tag['id'] for tag in soup.find_all(id=True)]
        if len(ids) != len(set(ids)):
            errors.append(f'{page.name}: duplicate anchor ids')
        for img in soup.find_all('img'):
            if not img.get('width') or not img.get('height'):
                errors.append(f'{page.name}: image dimensions missing: {img.get("src")}')
        for tag in soup.find_all(['a', 'link', 'script', 'img', 'object']):
            attribute = 'href' if tag.name in ('a', 'link') else 'data' if tag.name == 'object' else 'src'
            value = tag.get(attribute)
            if not value:
                continue
            url = urlsplit(value)
            # Converted manuals deliberately use literal command names as
            # anchors (e.g. #\tkzDefPoint). Validate those against actual IDs
            # below, while still rejecting unexpanded TeX in URL paths.
            if '\\' in value.partition('#')[0] or ('\\' in value and (url.scheme or url.netloc)):
                errors.append(f'{page.name}: unexpanded TeX in URL {value}')
            if url.scheme or url.netloc or value.startswith('/'):
                continue
            target = (page.parent / unquote(url.path)).resolve() if url.path else page
            # Package menus and cross-manual references leave this manual's
            # directory. Their targets are supplied by the other site builds.
            if not target.is_relative_to(root):
                continue
            if target.is_dir():
                target /= 'index.html'
            elif not target.suffix and target.with_name(target.name + '.html').is_file():
                target = target.with_name(target.name + '.html')  # /page serves page.html
            if not target.is_file():
                errors.append(f'{page.name}: missing file {value}')
            elif url.fragment and target in pages and unquote(url.fragment) not in anchors[target]:
                errors.append(f'{page.name}: missing anchor {value}')
        for tag in soup.select('script, style, [data-nosnippet], .example-code'):
            tag.decompose()
        # Three question marks in chemfig's historical prose are punctuation,
        # unlike the standalone two-character unresolved-reference marker.
        if re.search(r'(?<!\?)\?\?(?!\?)', soup.get_text()):
            errors.append(f'{page.name}: unresolved reference marker')
    if errors:
        raise ValueError('Invalid manual site:\n' + '\n'.join(errors))
    return dict(counts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    print(check_site(parser.parse_args().directory))
