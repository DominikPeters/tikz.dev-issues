#!/usr/bin/env python3
"""Finish lwarp's tikz-cd pages using the shared tikz.dev presentation."""
import copy
import datetime
import hashlib
import json
import re
from pathlib import Path
from shutil import copy2, copytree
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from check_manual_site import check_site
from illustration_formats import image_format
from lwarp_html import escape_code_angles, normalize_page_layout
from navbar import home_url, title_menu


PAGES = {
    'index.html': 'Commutative diagrams with TikZ',
    'getting-started.html': 'Getting started',
    'diagram-options.html': 'Controlling the appearance of diagrams',
    'advanced-usage.html': 'Advanced usage',
    'additional-goodies.html': 'Additional goodies',
}
IMAGES = 'tikz-cd-doc-images'
PDF_URL = 'https://mirrors.ctan.org/graphics/pgf/contrib/tikz-cd/tikz-cd-doc.pdf'
BASE_URL = 'https://tikz.dev/tikz-cd/'


def asset_url(name):
    version = hashlib.sha256(Path(name).read_bytes()).hexdigest()[:12]
    return f'{name}?v={version}'


def add_chrome(soup, filename, contents):
    container = soup.select_one('.bodyandsidetoc')
    container['class'].append('grid-container')
    for tag in soup.select('.topnavigation, .bottomnavigation, .botnavigation, .textbody > h1'):
        tag.decompose()
    sidebar = soup.select_one('.sidetoccontainer')
    if sidebar is None:
        sidebar = soup.new_tag('div', attrs={'class': 'sidetoccontainer'})
        container.insert(0, sidebar)
    sidebar['id'] = 'chapter-toc-container'
    sidebar.clear()
    nav = soup.new_tag('nav', attrs={'class': 'sidetoc', 'aria-label': 'Manual contents'})
    toc = soup.new_tag('div', attrs={'class': 'sidetoccontents'})
    for target, label in PAGES.items():
        p = soup.new_tag('p')
        a = soup.new_tag('a', href=target, attrs={'class': 'tocsection'})
        a.string = 'Overview' if target == 'index.html' else label
        if target == filename:
            p['class'] = 'current'
            a['aria-current'] = 'page'
        p.append(a)
        toc.append(p)
    nav.append(toc)
    sidebar.append(nav)

    header = soup.new_tag('header')
    hamburger = soup.new_tag('button', id='hamburger-button', type='button',
                              attrs={'aria-label': 'Toggle manual contents',
                                     'aria-controls': 'chapter-toc-container', 'aria-expanded': 'false'})
    hamburger.string = '☰'
    header.append(hamburger)
    title = soup.new_tag('strong')
    home = soup.new_tag('a', href=home_url('tikz-cd', 'pgf'),
                        style='font-weight: normal;')
    home.string = 'tikz.dev / '
    title.append(home)
    title.append(BeautifulSoup(title_menu('tikz-cd', 'tikz-cd Manual'), 'html.parser'))
    header.append(title)
    container.insert(0, header)

    local = soup.new_tag('div', id='local-toc-container',
                         attrs={'class': 'sidetoccontainer'})
    localnav = soup.new_tag('nav', attrs={'class': 'sidetoc', 'aria-label': 'On this page'})
    localtitle = soup.new_tag('div', attrs={'class': 'sidetoctitle'})
    p = soup.new_tag('p')
    p.string = 'On this page'
    localtitle.append(p)
    localnav.append(localtitle)
    localcontents = soup.new_tag('div', attrs={'class': 'sidetoccontents'})
    for heading in contents:
        p = soup.new_tag('p')
        number = heading.select_one('.sectionnumber[id]')
        target = number['id'] if number else heading['id']
        level = {'h4': 'tocsection', 'h5': 'tocsubsection', 'h6': 'tocsubsubsection'}[heading.name]
        a = soup.new_tag('a', href='#' + target, attrs={'class': level})
        clone = copy.deepcopy(heading)
        # A TOC entry must not duplicate ids or nest links in its own link.
        clone.attrs.pop('id', None)
        for child in clone.find_all(id=True):
            child.attrs.pop('id', None)
        for number in clone.select('.sectionnumber'):
            number['class'] = 'toc-number'
        for link in clone.select('.anchor-link'):
            link.decompose()
        for link in clone.find_all('a'):
            link.unwrap()
        clone.name = 'span'
        a.append(clone)
        p.append(a)
        localcontents.append(p)
    localnav.append(localcontents)
    local.append(localnav)
    container.append(local)

    footer = soup.new_tag('footer')
    left = soup.new_tag('div', attrs={'class': 'footer-left'})
    for label, url in [('CTAN', 'https://ctan.org/pkg/tikz-cd'),
                       ('Official PDF', PDF_URL),
                       ('Source and license', 'https://github.com/astoff/tikz-cd'),
                       ('Feedback and issues', 'https://github.com/DominikPeters/tikz.dev-issues/issues')]:
        if left.contents:
            left.append(' · ')
        a = soup.new_tag('a', href=url)
        a.string = label
        left.append(a)
    footer.append(left)
    right = soup.new_tag('div', attrs={'class': 'footer-right'})
    updated = soup.new_tag('em')
    updated.string = 'HTML version last updated: ' + datetime.date.today().isoformat()
    right.append(updated)
    footer.append(right)
    container.append(footer)


def finish_page(text, filename, formats, root):
    soup = BeautifulSoup(escape_code_angles(text), 'html5lib')
    normalize_page_layout(soup)
    soup.html['class'] = ['pkg-tikz-cd']
    if filename == 'index.html':
        soup.body['class'] = soup.body.get('class', []) + ['index-page']
    soup.title.string = PAGES[filename] + ' — tikz-cd Manual'
    for link in soup.select('link[rel="stylesheet"]'):
        if link.get('href') == 'style.css':
            link['href'] = asset_url('style.css')
    canonical = soup.new_tag('link', rel='canonical', href=BASE_URL + (
        '' if filename == 'index.html' else filename.removesuffix('.html')))
    soup.head.append(canonical)
    description = soup.new_tag('meta', attrs={'name': 'description', 'content':
        f'{PAGES[filename]}. Documentation and examples for tikz-cd, commutative diagrams with TikZ.'})
    soup.head.append(description)
    script = soup.new_tag('script', src=asset_url('pgfmanual.js'), defer='')
    soup.head.append(script)
    # Keep lwarp's generated hidden math macro definitions. Only externalize
    # its large emulation script; package-specific macros still reach MathJax.
    for script in soup.find_all('script'):
        if script.string and 'Lwarp MathJax emulation code' in script.string:
            script.replace_with(soup.new_tag('script', src=asset_url('lwarp-mathjax-emulation.js')))

    headings = []
    for heading in soup.select('.textbody h4, .textbody h5, .textbody h6'):
        number = heading.select_one('.sectionnumber')
        if number:
            number.string = number.get_text().strip()
            anchor = 'sec-' + number.get_text()
            # Keep lwarp's original anchors for existing references and index.
            number['id'] = anchor
        else:
            anchor = heading.get('id')
        if anchor:
            link = soup.new_tag('a', href='#' + anchor, attrs={'class': 'anchor-link',
                                                               'aria-label': 'Link to this section'})
            link.string = '¶'
            heading.append(link)
            headings.append(heading)
    # Include the title-page heading in the document outline, retaining logo.
    cover = soup.select_one('.textbody .center') if filename == 'index.html' else None
    if cover:
        for p in cover.find_all('p', recursive=False):
            if 'Commutative diagrams' in p.get_text():
                p.name = 'h1'
                p['class'] = 'manual-title'

    for table in soup.select('.textbody table'):
        table.wrap(soup.new_tag('div', attrs={'class': 'table-scroll', 'role': 'region',
                                               'aria-label': 'Scrollable table', 'tabindex': '0'}))

    for example in soup.select('.example'):
        example.name = 'figure'
    for headline in soup.select('.entryheadline'):
        target = headline.find('a', id=True)
        if target:
            link = soup.new_tag('a', href='#' + target['id'], attrs={'class': 'anchor-link',
                                                                    'aria-label': 'Link to this definition'})
            link.string = '¶'
            (headline.find('p') or headline).append(link)
    for area in soup.select('.example-code'):
        for p in area.find_all('p', recursive=False):
            p.name = 'code'
        for token in area.find_all(string=True):
            if '\u2007' not in token:
                continue
            # Preserve indentation as ordinary copyable spaces. HTML source
            # formatting newlines still collapse; only TeX's explicit spaces
            # get white-space preservation.
            for part in re.split('(\u2007+)', str(token)):
                if '\u2007' in part:
                    spaces = soup.new_tag('span', attrs={'class': 'spaces'})
                    spaces.string = part.replace('\u2007', ' ')
                    token.insert_before(spaces)
                elif part:
                    token.insert_before(part)
            token.extract()
        button = soup.new_tag('button', type='button', attrs={'class': 'clipboardButton',
                                                             'aria-label': 'Copy example code'})
        button.string = 'copy'
        area.insert(0, button)

    for img in soup.find_all('img'):
        src = img.get('src', '')
        if Path(src).parent.name != IMAGES:
            continue
        svg = ElementTree.parse(root / src).getroot()
        img['width'] = f'{float(svg.get("width").removesuffix("pt")) * 4 / 3:.3f}'
        img['height'] = f'{float(svg.get("height").removesuffix("pt")) * 4 / 3:.3f}'
        img['loading'] = 'lazy'
        force_svg = img.find_parent(class_='prefers-svg') is not None
        selected = image_format(src, formats, force_svg, images_directory=IMAGES)
        img['src'] = selected
        # lwarp links some image occurrences to their original SVG. Point the
        # download at the actual format shown on the page as well.
        parent = img.find_parent('a', href=src)
        if parent:
            parent['href'] = selected
    add_chrome(soup, filename, headings)
    return soup.decode(formatter='html5')


def main():
    root = Path.cwd()
    generated = {p.name for p in root.glob('*.html') if p.name != 'tikz-cd-doc_html.html'}
    if generated != set(PAGES):
        raise ValueError(f'Unexpected manual pages; review the page map: {sorted(generated ^ set(PAGES))}')
    formats = json.loads(Path('tikz-cd-image-formats.json').read_text())['images']
    output = Path('processed')
    output.mkdir(exist_ok=True)
    for name in ['style.css', 'pgfmanual.js', 'lwarp-mathjax-emulation.js']:
        copy2(name, output / name)
    copytree(IMAGES, output / IMAGES, dirs_exist_ok=True)
    for filename in PAGES:
        text = Path(filename).read_text()
        (output / filename).write_text(finish_page(text, filename, formats, root))
    result = check_site(output)
    print(f'tikz-cd site verified: {result}')


if __name__ == '__main__':
    main()
