#!/usr/bin/env python3
"""Convert the tkz-euclide manual to HTML in the style of tikz.dev.

The manual (doc/latex/TKZdoc-euclide-*.tex of the CTAN package) is written
with the tkz-doc class: commands are documented in NewMacroBox environments
with tables of arguments and options (\\TAline, \\TOline), and examples are
tkzexample environments, whose code is shown next to the picture it draws.
This script converts it with the shared converter in ../shared/texhtml (see
docs/converters.md); the pictures become images (tkzhtml.sty).

Usage:
    convert.py tex     write the instrumented LaTeX sources to build/tex
    convert.py html    write the HTML pages (uses images if present)
"""

import datetime
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)
from texhtml.core import (  # noqa: E402
    DEF_COLOR, IGNORED as BASE_IGNORED, Context, Converter, code_block, convert_pages, esc,
    instrument, load_images, match_brace, read_args, read_cs,
)
from texhtml.site import Manual, write_site  # noqa: E402

# the CTAN package at the pinned version (scripts/fetch.sh tkz-euclide)
UPSTREAM = os.environ.get("UPSTREAM", os.path.join(ROOT, ".upstream", "tkz-euclide"))
DOC = os.path.join(UPSTREAM, "doc", "latex")
BUILD = os.path.join(HERE, "build")
TEXDIR = os.path.join(BUILD, "tex")
SITE = os.path.join(BUILD, "site", "tkz-euclide")
IMGDIR_NAME = "tkz-euclide-images"
MAIN = "TKZdoc-euclide-main.tex"

# page names for the chapter files TKZdoc-euclide-<stem>.tex (default: the stem)
SLUGS = {
    "pointsSpc": "special-points", "pointby": "points-by-transformation",
    "pointwith": "points-with", "rnd": "random-points", "circleby": "circles-by-transformation",
    "FAQ": "faq", "lua": "lua", "documentation": "about-this-documentation",
    "others": "more-examples",
}

MIDNIGHTBLUE = "#191970"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_structure():
    """Parts and chapter files, in the order of the main file."""
    with open(os.path.join(DOC, MAIN), encoding="utf-8") as f:
        main = f.read()
    body = main[main.index("\\begin{document}"):]
    parts, chapters = [], []
    part = None
    for m in re.finditer(r"^\\part\{([^}]*)\}|^\\input\{TKZdoc-euclide-([\w-]+)(?:\.tex)?\}", body, re.M):
        if m.group(1):
            part = "part-" + slugify(m.group(1))  # part pages; chapter pages have the plain names
            parts.append((part, m.group(1)))
        else:
            stem = m.group(2)
            chapters.append((stem, SLUGS.get(stem, slugify(stem)), part))
    version = re.search(r"\\gdef\\tkzversionofpack\{([^}]*)\}", main).group(1)
    return parts, chapters, version


PARTS, CHAPTERS, VERSION = read_structure() if os.path.isdir(DOC) else ([], [], "")


def read_source(stem):
    with open(os.path.join(DOC, f"TKZdoc-euclide-{stem}.tex"), encoding="utf-8") as f:
        return f.read()


class TkzConverter(Converter):
    """Converter for the macros of the tkz-doc class."""

    verbatim_envs = Converter.verbatim_envs | {"tkzexample", "tkzltxexample", "Verbatim", "BVerbatim"}
    transparent_envs = Converter.transparent_envs | {"center", "landscape"}
    inline_image_commands = Converter.inline_image_commands | {"tkzTitleFrame"}
    ignored = dict(BASE_IGNORED, **{
        "Imacro": "m", "Ienv": "m", "Iarg": "mm", "Iopt": "mm", "Istyle": "mm",
        "MakeShortVerb": "m", "DeleteShortVerb": "m", "tkzSetUpColors": "om",
        "tkzSetUpCompass": "o", "tkzSetUpArc": "o", "tkzSetUpPoint": "o", "tkzSetUpLine": "o",
        "tkzSetUpLabel": "o", "tkzSetUpStyle": "om", "tkzSetUpAllLines": "o", "tkzSetUpAllPoints": "o",
        "tkzInit": "o", "tkzClip": "o", "defoffile": "m", "nameoffile": "m", "presentation": "",
        "tableofcontents": "", "emergencystretch": "", "parindent": "",
        "tkzSetUpDefaultColors": "o", "small": "", "footnotesize": "", "scriptsize": "",
    })
    img_dir = IMGDIR_NAME

    # -- text macros of tkz-doc ------------------------------------------------

    def _tt(self, e, out, prefix="", bold=False, color=None):
        args, e2 = read_args(self.s, e, "m")
        inner = esc(prefix) + self.inline(args[0])
        html = f'<span class="texttt">{inner}</span>'
        if color:
            html = f'<span class="textcolor" style="color: {color}">{html}</span>'
        if bold:
            html = f"<b>{html}</b>"
        out.append(("i", html))
        return e2

    def cmd_tkzcname(self, k, e, out):
        """\\tkzcname{name}: a command name, linked to its documentation."""
        args, e2 = read_args(self.s, e, "m")
        name = self.plain(args[0]).strip()
        label = self.ctx.known_commands.get(name)
        href = self.ctx.href(label, self.slug) if label else None
        inner = f'<span class="texttt">\\{esc(name)}</span>'
        if href:
            inner = f'<a href="{esc(href)}">{inner}</a>'
        out.append(("i", inner))
        return e2

    cmd_tkzhname = cmd_tkzcname
    cmd_tkzNameMacro = cmd_tkzcname

    def cmd_tkzname(self, k, e, out):
        return self._tt(e, out, bold=True)

    def cmd_tkzNameEnv(self, k, e, out):
        return self._tt(e, out, bold=True)

    def cmd_tkzimp(self, k, e, out):
        return self._wrap(e, out, "<b>", "</b>")

    def cmd_tkzdft(self, k, e, out):
        return self._tt(e, out)

    def cmd_code(self, k, e, out):
        return self._tt(e, out)

    def cmd_NameLib(self, k, e, out):
        return self._tt(e, out)

    cmd_NamePack = cmd_NameLib
    cmd_NameFonct = cmd_NameLib
    cmd_NameSys = cmd_NameLib
    cmd_NameDist = cmd_NameLib
    cmd_tkzNameSys = cmd_NameLib
    cmd_tkzNameDist = cmd_NameLib
    cmd_pkg = cmd_NameLib
    cmd_tkzNamePack = cmd_NameLib
    cmd_fn = cmd_NameLib
    cmd_env = cmd_NameLib

    def cmd_cn(self, k, e, out):
        return self._tt(e, out, prefix="\\")

    def cmd_addbs(self, k, e, out):
        return self._tt(e, out, prefix="\\")

    def cmd_IoptName(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        out.append(("i", f'<span class="texttt">{self.inline(args[1])}</span>'))
        return e2

    cmd_IargName = cmd_IoptName
    cmd_IoptNameEnv = cmd_IoptName
    cmd_IargNameEnv = cmd_IoptName

    def cmd_ItkzPopt(self, k, e, out):
        return self.cmd_IoptName(k, e, out)

    def cmd_parg(self, k, e, out):
        return self._delim_meta(e, out, "(", ")")

    def cmd_ooarg(self, k, e, out):
        return self._delim_meta(e, out, "[", "]")

    def cmd_opt(self, k, e, out):
        return self._wrap(e, out, "", "")

    def cmd_TIKZ(self, k, e, out):
        return self.cmd_tikzname(k, e, out)

    def cmd_PGF(self, k, e, out):
        out.append(("i", "PGF"))
        return e

    def cmd_tkznameofpack(self, k, e, out):
        out.append(("i", "tkz-euclide"))
        return e

    def _symbol(self, e, out, text):
        out.append(("i", text))
        if self.s.startswith("{}", e):
            e += 2
        return e

    def cmd_lefthand(self, k, e, out):
        return self._symbol(e, out, "☞")

    def cmd_tkzHand(self, k, e, out):
        return self._symbol(e, out, "<br />☞")

    def cmd_tkzHandBomb(self, k, e, out):
        return self._symbol(e, out, "<br />☞ 💣")

    def cmd_bomb(self, k, e, out):
        return self._symbol(e, out, "💣")

    def cmd_today(self, k, e, out):
        return self._symbol(e, out, datetime.date.today().strftime("%B %-d, %Y"))

    def cmd_red(self, k, e, out):
        return e

    def cmd_hypertarget(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        name = self.raw(args[0]).strip()
        if self.page is not None:
            anchor = re.sub(r"[^A-Za-z0-9_:.-]", "-", name)
            self.ctx.add_label(name, slug=self.slug, anchor=anchor, text=self.page.current_number, kind="label")
            out.append(("i", f'<a id="{esc(anchor)}"></a>' + self.inline(args[1])))
        return e2

    def cmd_hyperlink(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        out.append(("i", self._label_link(self.raw(args[0]).strip(), self.inline(args[1]))))
        return e2

    def cmd_var(self, k, e, out):
        return self.cmd_meta(k, e, out)

    def cmd_LATEX(self, k, e, out):
        return self.cmd_LaTeX(k, e, out)

    # -- documentation entries ---------------------------------------------------

    def env_NewMacroBox(self, k, a, b, after, out):
        """\\begin{NewMacroBox}{name}{signature}: a documented command."""
        args, a2 = read_args(self.s, a, "mm")
        name = self.raw(args[0]).strip()
        self.param_mode = True
        param = self.inline(args[1])
        self.param_mode = False
        label = f"com:{name}"
        anchor = "\\" + name
        # a command documented twice on a page (tkzSetUpStyle): number the second anchor
        used = self.page.__dict__.setdefault("entry_anchors", set())
        n = 2
        while anchor in used:
            anchor = f"\\{name}-{n}"
            n += 1
        used.add(anchor)
        self.ctx.add_label(label, slug=self.slug, anchor=anchor, text="\\" + name, kind="command")
        self.ctx.known_commands.setdefault(name, label)
        red = f'<span class="textcolor" style="color: {DEF_COLOR}">'
        headline = (f'<div class="entryheadline"><li><p><span class="hl-def"><kbd>\\{red}{esc(name)}</span></kbd>'
                    f'{param}</span><a class="anchor-link" href="#{esc(anchor)}" id="{esc(anchor)}">&para;</a>'
                    f"</p></li></div>")
        body = self.render(self.items(a2, b))
        out.append(("b", '<div class="manualentry"><ul class="list" style="list-style-type: none">'
                         + headline + body + "</ul></div>"))

    # -- tables of arguments and options -------------------------------------------

    env_tabular = Converter.env_html_table
    env_tabularx = Converter.env_html_table
    table_row_macros = ("TAline", "TOline", "TMline", "TOenvline")
    table_class = "tkz-table"

    def table_row_macro(self, name, k):
        """\\TAline{argument}{example}{explanation}, \\TOline{option}{default}{definition}, ..."""
        _, e = read_cs(self.s, k)
        args, e = read_args(self.s, e, "mmm")
        cells = [self.inline(args[0]), self.inline(args[1]), self.inline(args[2])]
        if name == "TMline":
            cells[0] = f'<span class="texttt">\\{cells[0]}</span>'
        else:
            cells[0] = f'<span class="texttt">{cells[0]}</span>'
        cells[1] = f'<span class="texttt">{cells[1]}</span>'
        return cells, e

    # -- examples ----------------------------------------------------------------

    def _example_options(self, a):
        """The optional argument of tkzexample, read from the verbatim body start."""
        s = self.s
        k = a
        while k < len(s) and s[k] in " \t":
            k += 1
        if k < len(s) and s[k] == "[":
            e = match_brace(s, k, "[", "]")
            return s[k + 1:e], e + 1
        return "", a

    def env_tkzexample(self, k, a, b, after, out, code_only=False):
        options, code_start = self._example_options(a)
        code = self.s[code_start:b]
        parts = []
        if not code_only and not re.search(r"code\s*only", options):
            image_id = self.new_image(k, None, "example")
            parts.append(f'<div class="example-image"><p>{self.img_html(image_id)}</p></div>')
        parts.append(code_block(code, self.ctx, self.slug))
        vertical = "vbox" in options
        cls = "example" + (" example-vertical" if vertical else "")
        out.append(("b", f'<figure class="{cls}">' + "".join(parts) + "</figure>"))

    def env_tkzltxexample(self, k, a, b, after, out):
        # LaTeX code that is shown, not run
        self.env_tkzexample(k, a, b, after, out, code_only=True)

    def env_Verbatim(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "o")
        out.append(("b", '<figure class="example">' + code_block(self.s[a2:b], self.ctx, self.slug) + "</figure>"))

    env_BVerbatim = env_Verbatim

    def env_verbatim(self, k, a, b, after, out):
        out.append(("b", '<figure class="example">' + code_block(self.s[a:b], self.ctx, self.slug) + "</figure>"))


MANUAL = Manual(
    package="tkz-euclide",
    title="tkz-euclide Manual",
    name_html="tkz-euclide",
    parts=PARTS,
    notice="""tkz-euclide documentation:
Copyright 2011-2026 Alain Matthes

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, version 1.3c.

tikz.dev:
Copyright 2021-2026 Dominik Peters
This file may be distributed and/or modified under the LaTeX Project Public License.""",
    footer_links=[("CTAN", "https://ctan.org/pkg/tkz-euclide"),
                  ("Official PDF version", "https://mirrors.ctan.org/macros/latex/contrib/tkz/tkz-euclide/doc/tkz-euclide.pdf"),
                  ("Source and license", "https://ctan.org/pkg/tkz-euclide")],
    build_dir=BUILD,
    site_dir=SITE,
    img_dir=IMGDIR_NAME,
    home_title="tkz-euclide Manual - Euclidean geometry with TikZ",
)


def convert_all(ctx):
    return convert_pages(ctx, CHAPTERS, read_source, TkzConverter, appendix_parts=())


def write_instrumented_tex(ctx, pages):
    shutil.copytree(DOC, TEXDIR, dirs_exist_ok=True)
    shutil.copy(os.path.join(SHARED, "texhtml", "tikzdev-capture.sty"), TEXDIR)
    shutil.copy(os.path.join(HERE, "tkzhtml.sty"), TEXDIR)
    for page in pages:
        s = instrument(read_source(page.stem), page.captures)
        with open(os.path.join(TEXDIR, f"TKZdoc-euclide-{page.stem}.tex"), "w", encoding="utf-8") as f:
            f.write(s)
    with open(os.path.join(DOC, MAIN), encoding="utf-8") as f:
        main = f.read()
    main = main.replace("\\usepackage{tkzexample}", "\\usepackage{tkzexample}\n\\usepackage{tkzhtml}")
    with open(os.path.join(TEXDIR, "tkz-euclide-html.tex"), "w", encoding="utf-8") as f:
        f.write(main)
    n = sum(1 for p in pages for c in p.captures if c[3] != "raw")
    print(f"Wrote instrumented sources to {TEXDIR} ({n} image fragments)")


def home_html(ctx, pages):
    sections = []
    for part_id, part_name in PARTS:
        lis = "".join(f'<li><a href="{p.slug}">{p.section_number}&ensp;{p.title_html}</a></li>'
                      for p in pages if p.part == part_id)
        sections.append(f'<div class="home-toc-section"><h3><a href="{part_id}">{part_name}</a></h3><ul>{lis}</ul></div>')
    return f"""
<div class="manual-title-block">
<div class="manual-title"><span class="texttt">tkz-euclide</span></div>
<div class="manual-version">Euclidean geometry with TikZ, version {VERSION}</div>
<div class="manual-authorship-explanation">Alain Matthes</div>
<div class="manual-html-title">HTML version of the official documentation</div>
<div class="manual-html-explanation">This is an unofficial HTML rendering of the
<a href="https://ctan.org/pkg/tkz-euclide">tkz-euclide</a> manual, generated from its LaTeX sources.</div>
</div>
<div class="abstract"><p class="abstract-title">Abstract</p><p><span class="texttt">tkz-euclide</span> is a set of
convenient macros for drawing figures in the plane with a Cartesian coordinate system. It handles the most
classic situations of Euclidean geometry. It is built on top of PGF and its front end TikZ, and lets you
construct figures step by step, as closely as possible to a construction made by hand.</p></div>
<div class="home-toc">{''.join(sections)}</div>
"""


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "html"
    ctx = Context()
    if mode == "html":
        load_images(ctx, os.path.join(BUILD, "images"))
    # pass 1: collect labels and documented commands; pass 2: produce final HTML
    ctx.pass_no = 1
    convert_all(ctx)
    ctx.pass_no = 2
    ctx.warnings.clear()
    pages = convert_all(ctx)
    if mode == "tex":
        write_instrumented_tex(ctx, pages)
    else:
        write_site(MANUAL, ctx, pages, home_html)
        print(f"Wrote {len(pages)} chapter pages to {SITE}")
    for msg, count in ctx.warnings.most_common(80):
        print(f"  warning ({count}x): {msg}")


if __name__ == "__main__":
    main()
