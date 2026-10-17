"""Start pages of the manuals: the title box and the contents.

The PGF and PGFplots manuals make their own start pages (with the title box
from patches of their sources); the other manuals use these helpers, the
converted manuals from their home_html and the lwarp manuals from
pgf_contrib_site.py, so that all start pages look alike.
"""
from html import escape

MAINTAINER = "Dominik Peters"
LWARP = '<a href="https://ctan.org/pkg/lwarp"><kbd>lwarp</kbd></a>'


def title_box(title, version="", author="", source_url="", logo="", tool="converter"):
    """The box at the top of a start page. Arguments are HTML, except
    source_url; tool is "lwarp" or "converter" (the Python converters)."""
    if tool == "lwarp":
        produced = f"and is produced using the {LWARP} package."
    else:
        produced = "and is generated from the LaTeX sources of the manual."
    lines = [f'<div class="manual-title-block home-box">']
    if logo:
        lines.append(f'<div class="manual-logo">{logo}</div>')
    lines.append(f'<h2 class="manual-title">{title}</h2>')
    if version:
        lines.append(f'<div class="manual-version">{version}</div>')
    lines.append('<div class="manual-html-title">Unofficial HTML Version</div>')
    lines.append(f'<div class="manual-html-explanation">This HTML version of the documentation is maintained '
                 f'by {MAINTAINER}, {produced}</div>')
    if author:
        lines.append(f'<div class="manual-authorship-explanation">{author}</div>')
    if source_url:
        lines.append(f'<div class="manual-authorship-explanation"><a href="{escape(source_url)}">'
                     f'{escape(source_url.removeprefix("https://"))}</a></div>')
    lines.append("</div>")
    return "\n".join(lines)


def contents(groups, heading="Contents"):
    """The contents as a grid of cards.

    groups: [(title HTML, href or None, number or "", [(number, title HTML, href)])]
    A card is a part with its chapters, or a page with its sections."""
    cards = []
    for title, href, number, items in groups:
        head = f'<span class="home-card-number">{number}</span>' if number else ""
        head += f'<a href="{escape(href)}">{title}</a>' if href else title
        lis = "".join(
            f'<li><span class="home-card-number">{n}</span><a href="{escape(h)}">{t}</a></li>'
            for n, t, h in items)
        cards.append('<section class="home-card">' + (f"<h3>{head}</h3>" if head else "")
                     + (f"<ol>{lis}</ol>" if lis else "") + "</section>")
    # a single list (a manual without subsections): one wider card
    cls = "home-contents home-contents-single" if len(groups) == 1 else "home-contents"
    return (f'<h2 class="home-contents-title">{heading}</h2>'
            f'<div class="{cls}">{"".join(cards)}</div>')
