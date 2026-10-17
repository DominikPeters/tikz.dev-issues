#!/usr/bin/env python3
"""Shared presentation for contributed manuals using PGF documentation macros."""
import copy
import datetime
from dataclasses import dataclass
import json
import re
from pathlib import Path
from shutil import copy2, copytree
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from assets import asset_url
from check_manual_site import check_site
from docsearch import add_docsearch
from illustration_formats import image_format
from lwarp_html import escape_code_angles, normalize_page_layout
from navbar import home_url, title_menu


@dataclass(frozen=True)
class Manual:
    package: str
    title: str
    jobname: str
    pages: dict[str, str]
    description: str
    pdf_url: str
    source_url: str
    cover_title: str = ''
    ignored_html: tuple[str, ...] = ()
    pair_adjacent_examples: bool = False
    page_aliases: tuple[tuple[str, str], ...] = ()

    @property
    def images(self):
        return self.jobname + '-images'

    @property
    def base_url(self):
        return 'https://tikz.dev/' + self.package + '/'


def add_chrome(soup, filename, contents, manual):
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
    for target, label in manual.pages.items():
        p = soup.new_tag('p')
        # like the parts in the PGF/PGFplots sidebars
        a = soup.new_tag('a', href=target,
                         attrs={'class': 'linkintro' if target == 'index.html' else 'tocpart'})
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
    home = soup.new_tag('a', href=home_url(manual.package, 'pgf'),
                        style='font-weight: normal;', attrs={'class': 'site-home-link'})
    home.string = 'tikz.dev / '
    title.append(home)
    title.append(BeautifulSoup(title_menu(manual.package, manual.title), 'html.parser'))
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
    # Like PGF, list the sections of the page, not its chapter heading.
    if [h.name for h in contents].count('h4') == 1 and contents[0].name == 'h4':
        contents = contents[1:]
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
            number.decompose()
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
    for label, url in [('CTAN', 'https://ctan.org/pkg/' + manual.package),
                       ('Official PDF', manual.pdf_url),
                       ('Source and license', manual.source_url),
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


def finish_page(text, filename, formats, root, manual):
    soup = BeautifulSoup(escape_code_angles(text), 'html5lib')
    normalize_page_layout(soup)
    aliases = dict(manual.page_aliases)
    for link in soup.select('a[href]'):
        target, separator, fragment = link['href'].partition('#')
        if target in aliases:
            link['href'] = aliases[target] + separator + fragment
    if manual.pair_adjacent_examples:
        for code in soup.select('.example-code'):
            output = code.find_next_sibling()
            if (output is None or output.name != 'p' or output.find('img') is None
                    or output.get_text(strip=True)):
                continue
            example = soup.new_tag('div', attrs={'class': 'example'})
            code.insert_before(example)
            image = soup.new_tag('div', attrs={'class': 'example-image'})
            image.append(output.extract())
            example.append(image)
            example.append(code.extract())
    soup.html['class'] = ['pkg-' + manual.package, 'pkg-pgf-contrib']
    if filename == 'index.html':
        soup.body['class'] = soup.body.get('class', []) + ['index-page']
    soup.title.string = manual.pages[filename] + ' - ' + manual.title
    for link in soup.select('link[rel="stylesheet"]'):
        if link.get('href') == 'style.css':
            link['href'] = asset_url('style.css', root)
    canonical = soup.new_tag('link', rel='canonical', href=manual.base_url + (
        '' if filename == 'index.html' else filename.removesuffix('.html')))
    soup.head.append(canonical)
    for attrs in [dict(rel='icon', type='image/png', sizes='16x16', href='/favicon-16x16.png'),
                  dict(rel='icon', type='image/png', sizes='32x32', href='/favicon-32x32.png'),
                  dict(rel='apple-touch-icon', type='image/png', sizes='180x180', href='/apple-touch-icon.png'),
                  dict(rel='manifest', href='/site.webmanifest')]:
        soup.head.append(soup.new_tag('link', attrs=attrs))
    for prop, content in [('og:url', canonical['href']), ('og:type', 'article'),
                          ('og:title', soup.title.string)]:
        soup.head.append(soup.new_tag('meta', attrs={'property': prop, 'content': content}))
    soup.head.append(soup.new_tag('meta', attrs={'name': 'twitter:card', 'content': 'summary'}))
    description = soup.new_tag('meta', attrs={'name': 'description', 'content':
        f'{manual.pages[filename]}. {manual.description}'})
    soup.head.append(description)
    script = soup.new_tag('script', src=asset_url('pgfmanual.js', root), defer='')
    soup.head.append(script)
    # Keep lwarp's generated hidden math macro definitions. Only externalize
    # its large emulation script; package-specific macros still reach MathJax.
    for script in soup.select('script[src$="/tex-svg.js"]'):
        script['src'] = script['src'].removesuffix('tex-svg.js') + 'tex-chtml.js'
        script['async'] = ''
    for script in soup.find_all('script'):
        if script.string and 'Lwarp MathJax emulation code' in script.string:
            script.replace_with(soup.new_tag('script', src=asset_url('lwarp-mathjax-emulation.js', root)))

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
        # Keep formatted title fragments together as one flex item. Otherwise
        # the shared heading layout loses spaces around emphasis and cannot
        # wrap a heading such as "Commands & Environments" on a narrow phone.
        label = soup.new_tag('span', attrs={'class': 'heading-title'})
        for child in list(heading.contents):
            if child is not number:
                label.append(child.extract())
        heading.append(label)
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
            if manual.cover_title and manual.cover_title in p.get_text():
                p.name = 'h1'
                p['class'] = 'manual-title'

    if filename == 'index.html':
        for heading in soup.select('.titlepage h1'):
            heading['class'] = ['manual-title']

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
        for listing in area.select('pre.programlisting'):
            # Listings already preserves its newlines and indentation. Give
            # the common clipboard handler a code element without flattening it.
            listing.name = 'code'
        for p in area.find_all('p', recursive=False):
            p.name = 'code'
        for code in area.find_all('code', recursive=False):
            # lwarp starts some listings with a line break: no empty first line
            while code.contents and (code.contents[0].name == 'br' or
                                     (isinstance(code.contents[0], str) and not code.contents[0].strip())):
                code.contents[0].extract()
            if code.contents and isinstance(code.contents[0], str):
                code.contents[0].replace_with(code.contents[0].lstrip('\n'))
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
        if Path(src).parent.name != manual.images:
            continue
        svg = ElementTree.parse(root / src).getroot()
        img['width'] = f'{float(svg.get("width").removesuffix("pt")) * 4 / 3:.3f}'
        img['height'] = f'{float(svg.get("height").removesuffix("pt")) * 4 / 3:.3f}'
        img['loading'] = 'lazy'
        force_svg = img.find_parent(class_='prefers-svg') is not None
        selected = image_format(src, formats, force_svg, images_directory=manual.images)
        img['src'] = selected
        # lwarp links some image occurrences to their original SVG. Point the
        # download at the actual format shown on the page as well.
        parent = img.find_parent('a', href=src)
        if parent:
            parent['href'] = selected
    add_chrome(soup, filename, headings, manual)
    add_docsearch(soup)
    # Link to the manual's pages without .html, as the other manuals and the
    # canonical URLs do (the server resolves /page to page.html).
    pages = {name.removesuffix('.html') for name in manual.pages}
    for link in soup.select('a[href]'):
        target, separator, fragment = link['href'].partition('#')
        name = target.removesuffix('.html')
        if target.endswith('.html') and name in pages:
            link['href'] = ('./' if name == 'index' else name) + separator + fragment
    return soup.decode(formatter='html5')


def build_site(manual):
    root = Path.cwd()
    generated = {p.name for p in root.glob('*.html') if p.name not in (manual.jobname + '_html.html', *manual.ignored_html)}
    aliases = dict(manual.page_aliases)
    canonical = {aliases.get(name, name) for name in generated}
    if canonical != set(manual.pages) or len(canonical) != len(generated):
        raise ValueError(f'Unexpected manual pages; review the page map: {sorted(canonical ^ set(manual.pages))}')
    formats = json.loads(Path(manual.package + '-image-formats.json').read_text())['images']
    output = Path('processed')
    output.mkdir(exist_ok=True)
    for name in ['style.css', 'pgfmanual.js', 'lwarp-mathjax-emulation.js']:
        copy2(name, output / name)
    copytree(manual.images, output / manual.images, dirs_exist_ok=True)
    for filename in manual.pages:
        source = next((old for old, new in manual.page_aliases if new == filename), filename)
        text = Path(source).read_text()
        (output / filename).write_text(finish_page(text, filename, formats, root, manual))
    result = check_site(output)
    print(f'{manual.package} site verified: {result}')
