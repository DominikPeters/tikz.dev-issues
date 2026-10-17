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

from bs4 import BeautifulSoup, Comment

from assets import asset_url
from check_manual_site import check_site
from docsearch import add_docsearch
from citations import entry_label, unique
from home import contents, find_examples, showcase, title_box
from illustration_formats import image_format
from lwarp_html import escape_code_angles, normalize_page_layout
from navbar import ISSUES_URL, REPO_URL, home_url, title_menu


@dataclass(frozen=True)
class Manual:
    package: str
    title: str
    jobname: str
    pages: dict[str, str]
    description: str
    pdf_url: str
    source_url: str
    notice: str  # copyright and license of the documentation, for the comment atop each page
    cover_title: str = ''
    ignored_html: tuple[str, ...] = ()
    pair_adjacent_examples: bool = False
    page_aliases: tuple[tuple[str, str], ...] = ()
    author: str = ''  # of the documentation, for the start page
    # examples whose pictures the start page shows: (page, fragment of the code without whitespace)
    showcase: tuple[tuple[str, str], ...] = ()

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
                       ('Official PDF version', manual.pdf_url),
                       ('Source and license', manual.source_url),
                       ('Feedback and issues', ISSUES_URL),
                       ('About this HTML version', REPO_URL)]:
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


def finish_page(text, filename, formats, root, manual, home_groups=None, home_examples=(), bibliography=None):
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
        rebuild_home(soup, manual, home_groups, home_examples)
        # the new start page replaces some headings (Contents, the cover)
        headings = [h for h in headings if not h.decomposed and h.find_parent(class_='textbody')]
    if bibliography:
        expand_citations(soup, filename, bibliography)

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
        # (the start page's examples come from finished pages: already converted)
        if Path(src).parent.name != manual.images or Path(src).suffix != '.svg':
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
    soup.html.insert(0, Comment(f'''{manual.notice.strip()}

Translated to HTML using the lwarp package:
Copyright 2016-2026 Brian Dunn - BD Tech Concepts LLC

tikz.dev:
Copyright 2021-2026 Dominik Peters
This file may be distributed and/or modified under the same license as the
documentation.'''))
    # Link to the manual's pages without .html, as the other manuals and the
    # canonical URLs do (the server resolves /page to page.html).
    pages = {name.removesuffix('.html') for name in manual.pages}
    for link in soup.select('a[href]'):
        target, separator, fragment = link['href'].partition('#')
        name = target.removesuffix('.html')
        if target.endswith('.html') and name in pages:
            link['href'] = ('./' if name == 'index' else name) + separator + fragment
    return soup.decode(formatter='html5')


MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'
DATE_RE = re.compile(rf'\d{{4}}/\d\d/\d\d|(?:{MONTHS})\s+\d{{1,2}},\s*\d{{4}}'
                     rf'|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+\d{{4}}')
VERSION_RE = re.compile(r'(?:\bVersion\s+|\bv)(\d[\w.]*)')


def heading_html(heading):
    """The title of a section heading, without its number and anchor link."""
    heading = copy.copy(heading)
    for tag in heading.select('.sectionnumber, a.anchor-link'):
        tag.decompose()
    title = heading.select_one('.heading-title') or heading
    return title.decode_contents().strip()


def home_contents(manual, read):
    """The cards of the start page: one per page, with its numbered subsections."""
    groups = []
    for filename, label in manual.pages.items():
        if filename == 'index.html':
            continue
        soup = BeautifulSoup(read(filename), 'html5lib')
        href = filename.removesuffix('.html')
        number, items = '', []
        for heading in soup.select('.textbody h4, .textbody h5'):
            mark = heading.select_one('.sectionnumber')
            num = mark.get_text(strip=True) if mark else ''
            if heading.name == 'h4':
                number = number or num
            elif num:
                items.append((num, heading_html(heading), f'{href}#sec-{num}'))
        groups.append((escape_html(label), href, number, items))
    if not any(items for *_, items in groups):  # no subsections: one list of the pages
        groups = [('', None, '', [(number, title, href) for title, href, number, _ in groups])]
    return groups


def escape_html(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def rebuild_home(soup, manual, groups, examples=()):
    """Replace lwarp's title page and table of contents by the shared start
    page (shared/home.py): the title box and the contents as cards."""
    textbody = soup.select_one('.textbody')
    title = textbody.select_one('h1.manual-title') if textbody else None
    if title is None:
        return
    cover = title.find_parent(class_='center') or title.find_parent(class_='titlepage') or title
    # a logo drawn above the title
    logo = ''
    image = title.find_previous('img')
    if image is not None and cover in image.parents:
        source = image.find_parent(class_='lateximagesource') or image
        logo = str(source)
    # a blank line in the title separates a subtitle (a single line break does not)
    parts = [part.strip() for part in re.split(r'\s*<br/?>\s*(?:<br/?>\s*)+', title.decode_contents()) if part.strip()]
    heading, subtitle = parts[0], ' '.join(parts[1:])
    text = ' '.join(cover.get_text(' ').replace(title.get_text(' '), ' ').split())
    version = VERSION_RE.search(text)
    date = DATE_RE.search(text)
    today = datetime.date.today()
    if date and date.group(0) in (f'{today:%B} {today.day}, {today.year}', f'{today:%Y/%m/%d}'):
        date = None  # \today: the date of the build, not of the manual
    version_line = ''
    if version:
        version_line = ('version ' if subtitle else 'Version ') + version.group(1)
    if date:
        version_line += f' ({date.group(0)})' if version_line else date.group(0)
    if subtitle:
        version_line = subtitle + (', ' + version_line if version_line else '')
    name = manual.title.removesuffix(' Manual')
    box = BeautifulSoup(title_box(
        heading, version_line, f'Author of the {name} manual: {manual.author}.' if manual.author else '',
        manual.source_url, logo, tool='lwarp'), 'html.parser').div
    top = cover
    while top.parent is not textbody:
        top = top.parent
    top.insert_before(box)
    cover.decompose()
    if top is not cover and not top.get_text(strip=True) and top.find('img') is None:
        top.decompose()
    following = box.find_next_sibling()
    while following is not None and following.name == 'a' and not following.get_text(strip=True):
        following = following.find_next_sibling()
    if following is not None and 'footnotes' in following.get('class', []):
        following.decompose()  # footnotes of the title page (affiliations)

    if groups is None:
        return
    # lwarp's table of contents (or a picture of it) gives way to the cards
    anchor = None
    for contents_heading in textbody.select('h4, h5'):
        if contents_heading.get_text(' ', strip=True).startswith('Contents'):
            anchor = contents_heading
            for sibling in list(contents_heading.find_next_siblings()):
                if sibling.name == 'nav' or 'example' in sibling.get('class', []) or (
                        sibling.name == 'a' and not sibling.get_text(strip=True)):
                    sibling.decompose()
                else:
                    break
            break
    for toc in textbody.select('nav.toc'):
        container = toc.find_parent(class_='multicols')
        toc.decompose()
        if container is not None and not container.get_text(strip=True):
            container.decompose()
    cards = BeautifulSoup(showcase(examples) + contents(groups), 'html.parser')
    if anchor is not None:
        top = anchor
        while top.parent is not textbody:
            top = top.parent
        top.insert_after(cards)
        anchor.decompose()
        if top is not anchor and not top.get_text(strip=True) and top.find('img') is None:
            top.decompose()
    else:
        textbody.append(cards)


BIB_MARKER = re.compile(r'^\[(\d+)\]$')
CITATION = re.compile(r'\[(\d{1,3})\]')
NOT_PROSE = {'code', 'kbd', 'pre', 'script', 'style', 'a', 'samp'}


def bibliography_items(soup):
    """The entries of a numbered reference list: [(number, li)]."""
    items = []
    for li in soup.select('li'):
        marker = li.select_one('.listmarker')
        match = BIB_MARKER.match(marker.get_text(strip=True)) if marker else None
        heading = li.find_previous(['h4', 'h5'])
        if match and heading and re.search(r'Reference|Bibliograph', heading.get_text()):
            items.append((match.group(1), li))
    return items


def collect_bibliography(manual, read):
    """Author-year labels for the numbered references of a manual:
    {number: {label, href, title}}, from the page that lists them."""
    entries = {}
    for filename in manual.pages:
        soup = BeautifulSoup(read(filename), 'html5lib')
        for number, li in bibliography_items(soup):
            marker = li.select_one('.listmarker')
            text = ' '.join(li.get_text(' ').replace(marker.get_text(), '', 1).split())
            title = li.find('em')
            start = text.find('\u2018')
            if title is not None and title.get_text(strip=True):
                em_start = text.find(' '.join(title.get_text(' ').split()))
                start = em_start if start < 0 or 0 <= em_start < start else start
            authors, rest = (text[:start], text[start:]) if start > 0 else (text.split(',')[0], text)
            target = li.find('a', id=True)
            anchor = target['id'] if target else f'ref-{number}'
            href = ('' if filename == 'index.html' else filename.removesuffix('.html')) + '#' + anchor
            entries[number] = {'label': entry_label(authors, rest), 'href': href, 'title': text,
                               'page': filename}
    labels = unique({n: e['label'] or n for n, e in entries.items()})
    for number, entry in entries.items():
        entry['label'] = labels[number]
    return entries


def expand_citations(soup, filename, bibliography):
    """[5] becomes [Tantau 2025], linked to the reference (also in the list)."""
    textbody = soup.select_one('.textbody')
    if textbody is None:
        return
    if any(entry['page'] == filename for entry in bibliography.values()):
        for number, li in bibliography_items(soup):
            if number in bibliography:
                li.select_one('.listmarker').string = f"[{bibliography[number]['label']}] "
                if li.find('a', id=True) is None:
                    li['id'] = f'ref-{number}'
    # citations that lwarp linked: [<a href="references#cite...">2</a>]
    for link in textbody.select('a[href]'):
        number = link.get_text(strip=True)
        entry = bibliography.get(number)
        if entry and link['href'].endswith('#' + entry['href'].split('#')[1]):
            link.string = entry['label']
            link['title'] = entry['title']
    # citations in plain text: [5]
    for text in list(textbody.find_all(string=CITATION)):
        if isinstance(text, Comment) or any(parent.name in NOT_PROSE or
                                            set(parent.get('class', [])) & {'example-code', 'verb', 'listmarker'}
                                            or parent.has_attr('data-nosnippet') for parent in text.parents):
            continue
        parts = []
        last = 0
        for match in CITATION.finditer(text):
            entry = bibliography.get(match.group(1))
            if entry is None:
                continue
            parts.append(text[last:match.start()])
            link = soup.new_tag('a', href=entry['href'], title=entry['title'])
            link.string = entry['label']
            parts.extend(['[', link, ']'])
            last = match.end()
        if not parts:
            continue
        parts.append(text[last:])
        for part in parts:
            text.insert_before(part)
        text.extract()


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
    sources = {filename: Path(next((old for old, new in manual.page_aliases if new == filename), filename))
               for filename in manual.pages}
    groups = home_contents(manual, lambda filename: sources[filename].read_text())
    bibliography = collect_bibliography(manual, lambda filename: sources[filename].read_text())
    # the start page last: its showcase takes pictures from the finished pages
    for filename in sorted(manual.pages, key=lambda name: name == 'index.html'):
        text = sources[filename].read_text()
        examples = ()
        if filename == 'index.html':
            examples = find_examples({name: (output / name).read_text() for name, _ in manual.showcase},
                                     manual.showcase)
        (output / filename).write_text(finish_page(text, filename, formats, root, manual, groups, examples,
                                                   bibliography))
    result = check_site(output)
    print(f'{manual.package} site verified: {result}')
