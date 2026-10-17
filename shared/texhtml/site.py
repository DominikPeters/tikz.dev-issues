"""Pages of a converted manual: the tikz.dev page shell, part pages, references."""

import datetime
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Callable

SHARED = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SHARED)
from assets import asset_url  # noqa: E402
from docsearch import DOCSEARCH_ASSETS  # noqa: E402
from navbar import ISSUES_URL, REPO_URL, home_url, title_menu  # noqa: E402

from .core import Page, esc, fix_page_refs, footnotes_html, tex_to_text  # noqa: E402


@dataclass
class Manual:
    package: str                 # also the folder on tikz.dev and the <html> class pkg-<package>
    title: str                   # "tcolorbox Manual": header menu and page titles
    name_html: str               # "The tcolorbox package": sidebar title and <h1>
    parts: list                  # [(part id, part name)]; part pages are written for each
    notice: str                  # copyright comment atop every page
    footer_links: list           # [(label, url)] before "Feedback and issues", "About ..."
    build_dir: str               # images are read from <build_dir>/images
    site_dir: str                # output folder
    img_dir: str                 # folder of the images on the site
    home_title: str = ""         # <title> of the start page
    toc_title: Callable = field(default=lambda page: page.title_html)

    @property
    def base_url(self):
        return f"https://tikz.dev/{self.package}/"


def page_shell(manual, pages, page, title, main_html, local_toc, is_home=False):
    today = datetime.date.today().isoformat()
    style_url = asset_url('style.css', SHARED)
    script_url = asset_url('pgfmanual.js', SHARED)
    parts = dict(manual.parts)
    # chapter toc
    toc = ['<p></p>']
    cls = ' class="current"' if is_home else ""
    toc.append(f'<p{cls}><a class="linkintro" href="./">Home</a></p>')
    current_part = page.part if page else None
    for part_id, part_name in manual.parts:
        pcls = []
        if part_id == current_part:
            pcls.append("current-part")
        if page is not None and page.slug == part_id:
            pcls.append("current")
        c = f' class="{" ".join(pcls)}"' if pcls else ""
        toc.append(f'<p{c}><a class="tocpart" href="{part_id}">{part_name}</a></p>')
        if part_id == current_part:
            for p in pages:
                if p.part != part_id:
                    continue
                c = ' class="current current-part"' if p is page else ' class="current-part"'
                toc.append(f'<p{c}><a class="tocsection" href="{p.slug}">{manual.toc_title(p)}</a></p>')
    local = "".join(f'<p><a class="{c}" href="#{a}">{t}</a></p>' for c, a, t in local_toc)
    mathjax = ""
    if page is not None and page.uses_math:
        mathjax = '<script async id="MathJax-script" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>'
    part_h2 = ""
    if page is not None and page.part is not None and page.slug not in parts:
        part_h2 = f'<h2 class="inserted">{parts[page.part]}</h2>'
    canonical = manual.base_url + ("" if is_home else page.slug)
    footer = " &middot;\n".join(
        [f'<a href="{esc(url)}">{label}</a>' for label, url in manual.footer_links]
        + [f'<a href="{ISSUES_URL}">Feedback and issues</a>', f'<a href="{REPO_URL}">About this HTML version</a>'])
    return f"""<!DOCTYPE html>
<html class="pkg-{manual.package}" lang="en-US">
<!--{manual.notice.strip()}-->
<head>
<meta charset="utf-8" />
<meta content="width=device-width, initial-scale=1.0" name="viewport" />
<title>{esc(title)}</title>
<link href="{style_url}" rel="stylesheet" type="text/css" />
{DOCSEARCH_ASSETS}
{mathjax}
<script src="{script_url}"></script>
<link href="/favicon-16x16.png" rel="icon" sizes="16x16" type="image/png" />
<link href="/favicon-32x32.png" rel="icon" sizes="32x32" type="image/png" />
<link href="{canonical}" rel="canonical" />
<meta content="{canonical}" property="og:url" />
<meta content="article" property="og:type" />
<meta content="{esc(title)}" property="og:title" />
<meta content="summary" name="twitter:card" />
</head>
<body{' class="index-page"' if is_home else ''}>
<div class="bodyandsidetoc grid-container">
<header>
<div id="hamburger-button">☰</div>
<strong><a class="site-home-link" href="{home_url(manual.package, "pgf")}" style="font-weight: normal">tikz.dev / </a>{title_menu(manual.package, manual.title)}</strong>
<div id="search"></div>
</header>
<div class="sidetoccontainer" id="local-toc-container">
<nav class="sidetoc">
<div class="sidetoctitle"><p>On this page</p></div>
<div class="sidetoccontents">{local}</div>
</nav>
</div>
<div class="sidetoccontainer" id="chapter-toc-container">
<nav class="sidetoc">
<div class="sidetoctitle"><p><span class="sidetocthetitle">{manual.name_html}</span></p><p>Contents</p></div>
<div class="sidetoccontents">
{chr(10).join(toc)}
</div>
</nav>
</div>
<main class="bodycontainer">
<section class="textbody">
<h1>{manual.name_html}</h1>
{part_h2}
{main_html}
</section>
</main>
<footer>
<div class="footer-left">
{footer}
</div>
<div class="footer-right"><em>HTML version last updated: {today}</em></div>
</footer>
</div>
</body>
</html>
"""


def write_site(manual, ctx, pages, home_html):
    """Write the chapter pages, part pages, references (if anything is cited)
    and the start page. home_html(ctx, pages) returns the start page's main
    content; it is called after the images have been copied to the site."""
    os.makedirs(manual.site_dir, exist_ok=True)
    for name in ("style.css", "pgfmanual.js"):
        shutil.copy(os.path.join(SHARED, name), manual.site_dir)
    img_src = os.path.join(manual.build_dir, "images")
    if os.path.isdir(img_src):
        dst = os.path.join(manual.site_dir, manual.img_dir)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(img_src, dst, ignore=shutil.ignore_patterns("*.pdf", "dims.json"))
    for page in pages:
        main = page.body + footnotes_html(page)
        main = fix_page_refs(main)
        out = page_shell(manual, pages, page, f"{page.title} - {manual.title}", main, page.toc)
        with open(os.path.join(manual.site_dir, page.slug + ".html"), "w", encoding="utf-8") as f:
            f.write(out)
    # part pages
    for part_id, part_name in manual.parts:
        part_page = Page(None, part_id, part_id, "")
        part_page.title_html = part_name
        items = "".join(f'<li><a href="{p.slug}">{p.section_number}&ensp;{manual.toc_title(p)}</a></li>'
                        for p in pages if p.part == part_id)
        main = f'<h3>{part_name}</h3><div class="mobile-toc part-toc"><ul>{items}</ul></div>'
        with open(os.path.join(manual.site_dir, part_id + ".html"), "w", encoding="utf-8") as f:
            f.write(page_shell(manual, pages, part_page, f"{part_name} - {manual.title}", main, []))
    if ctx.cited:
        # in the appendix part if the manual has one (tcolorbox)
        write_references(manual, ctx, pages, part="appendix" if "appendix" in dict(manual.parts) else None)
    home_page = Page(None, "index", None, "")
    with open(os.path.join(manual.site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page_shell(manual, pages, home_page, manual.home_title or manual.title, home_html(ctx, pages), [],
                           is_home=True))


def write_references(manual, ctx, pages, part="appendix"):
    entries = []
    for key in ctx.cited_sorted:
        e = ctx.bib.get(key, {})
        n = ctx.cite_numbers[key]
        author = tex_to_text(e.get("author", e.get("editor", ""))).replace(" and ", ", ")
        title = tex_to_text(e.get("title", key))
        rest = []
        for field_name in ("subtitle", "edition", "publisher", "location", "organization", "date", "year"):
            if e.get(field_name):
                val = tex_to_text(e[field_name])
                if field_name == "edition" and val.isdigit():
                    val = f"{val}. edition"
                rest.append(val)
        url = e.get("url", "")
        url_html = f'<br /><a href="{esc(url)}">{esc(url)}</a>' if url else ""
        entries.append(f'<p class="bibitem" id="{esc(key)}"><span class="biblabel">[{n}]</span> '
                       f'{esc(author)}. <i>{esc(title)}</i>. {esc(". ".join(rest))}{"." if rest else ""}{url_html}</p>')
    ref_page = Page(None, "references", part, "")
    ref_page.title_html = "References"
    main = '<h4><span><span class="sectionnumber" id="sec-refs"></span> References</span></h4>' + "".join(entries)
    with open(os.path.join(manual.site_dir, "references.html"), "w", encoding="utf-8") as f:
        f.write(page_shell(manual, pages, ref_page, f"References - {manual.title}", main, []))


def sort_citations(ctx):
    """Number the cited works by author, year and title (call after pass 1)."""
    def sort_key(key):
        e = ctx.bib.get(key, {})
        return (tex_to_text(e.get("author", e.get("editor", "zzz"))).split(",")[0].split()[-1:],
                e.get("year", e.get("date", "")), e.get("title", ""))
    ctx.cited_sorted = sorted(ctx.cited, key=sort_key)
    ctx.cite_numbers = {k: i + 1 for i, k in enumerate(ctx.cited_sorted)}
