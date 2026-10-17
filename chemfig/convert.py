#!/usr/bin/env python3
"""Convert the chemfig manual to HTML in the style of tikz.dev.

The manual (chemfig-en.tex of the CTAN package) is one LaTeX file with parts
and sections; every section becomes a page. Examples are \\exemple{title}|code|
(the code is shown next to the molecule it draws); molecules in running text
(\\chemfig, reaction schemes, ...) become images too. The key tables print the
default value of each key, which the converter reads from chemfig.tex. This
script uses the shared converter in ../shared/texhtml (see docs/converters.md);
the molecules are captured by chemhtml.sty.

Usage:
    convert.py tex     write the instrumented LaTeX sources to build/tex
    convert.py html    write the HTML pages (uses images if present)
"""

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)
from texhtml.core import (  # noqa: E402
    IGNORED as BASE_IGNORED, Context, Converter, Page, code_block, esc, instrument, load_images,
    match_brace, read_args, read_cs, split_kv, tex_to_text,
)
from texhtml.site import Manual, write_site  # noqa: E402

# the CTAN package at the pinned version (scripts/fetch.sh chemfig)
UPSTREAM = os.environ.get("UPSTREAM", os.path.join(ROOT, ".upstream", "chemfig"))
DOC = UPSTREAM
BUILD = os.path.join(HERE, "build")
TEXDIR = os.path.join(BUILD, "tex")
SITE = os.path.join(BUILD, "site", "chemfig")
IMGDIR_NAME = "chemfig-images"
MAIN = "chemfig-en.tex"
TEAL = "#008080"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def heading_text(tex):
    """Plain text of a heading argument (for page names)."""
    tex = tex.replace("\\protect", "").replace("\\CF", "chemfig").replace("\\textbackslash", "")
    tex = re.sub(r"\\char`\\\\", "", tex)
    return " ".join(tex_to_text(tex).replace("{", "").replace("}", "").split())


# --------------------------------------------------------------------------
# The source: one file, split into chunks at \part and \section
# --------------------------------------------------------------------------

def read_main():
    with open(os.path.join(DOC, MAIN), encoding="utf-8") as f:
        text = f.read()
    # the change history is \input; make it part of the text (also for LaTeX)
    with open(os.path.join(DOC, "changelog.tex"), encoding="utf-8") as f:
        changelog = f.read()
    return text.replace("\\input{changelog.tex}", changelog)


def split_chunks(text):
    """(preamble up to the first part, [(kind, title, start, end)], rest from \\end{document})."""
    first = re.search(r"^\\part\{", text, re.M).start()
    end = text.index("\\end{document}")
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"^\\(part|section)\{", text, re.M)
             if first <= m.start() < end]
    chunks = []
    for i, (pos, kind) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else end
        brace = text.index("{", pos)
        title = text[brace + 1:match_brace(text, brace)]
        chunks.append((kind, title, pos, stop))
    return text[:first], chunks, text[end:]


def read_structure():
    """Parts and pages: (chunk id, page name, part id, numbered?)."""
    text = read_main()
    _, chunks, _ = split_chunks(text)
    parts, pages, sources = [], [], {}
    part_labels = []  # (label, part) of parts that get no page of their own
    used = set()
    part = None
    for i, (kind, title, start, stop) in enumerate(chunks):
        name = heading_text(title)
        body = text[start:stop]
        if kind == "part":
            part = "part-" + slugify(name)
            parts.append((part, name))
            # text between \part and its first \section (or a part without sections)
            rest = re.sub(r"^\\part\{.*?\}(\\label\{[^}]*\})?", "", body, flags=re.S)
            if not re.sub(r"%[^\n]*", "", rest).strip():
                part_labels.extend((lb, part) for lb in re.findall(r"\\label\{([^}]*)\}", body))
                continue
            slug = slugify(name)
        else:
            slug = slugify(name)
        if slug in used:
            slug = slugify(dict(parts)[part].split()[0]) + "-" + slug
        used.add(slug)
        cid = f"c{i:02d}"
        sources[cid] = body
        pages.append((cid, slug, part, kind == "section"))
    return parts, pages, sources, text, part_labels


PARTS, PAGES, SOURCES, TEXT, PART_LABELS = read_structure() if os.path.isdir(DOC) else ([], [], {}, "", [])


def read_defaults():
    """Default values of the keys (\\setKVdefault[family]{...} in chemfig.tex)."""
    with open(os.path.join(DOC, "chemfig.tex"), encoding="utf-8") as f:
        src = f.read()
    defaults = {}
    for m in re.finditer(r"\\setKVdefault\[(\w+)\]\{", src):
        brace = m.end() - 1
        body = src[brace + 1:match_brace(src, brace)]
        values = {}
        for key, val in split_kv(body, 0, len(body)):
            values[key] = "" if val is None else body[val[0]:val[1]].strip()
        defaults[m.group(1)] = values
    return defaults


# --------------------------------------------------------------------------
# The converter
# --------------------------------------------------------------------------

class ChemConverter(Converter):
    """Converter for the macros of the chemfig manual."""

    verbatim_envs = Converter.verbatim_envs | {"titlepage"}
    inline_image_commands = Converter.inline_image_commands | {
        "chemfig", "chemname", "charge", "Charge", "chemabove", "chembelow", "chemleft", "chemright",
        "lewis", "Lewis", "chemmove", "molht", "chemsign", "chemrel", "subscheme",
    }
    inline_image_specs = dict(Converter.inline_image_specs, **{
        "chemfig": "*oom", "chemname": "*oomm", "charge": "omm", "Charge": "omm", "chemabove": "*omm",
        "chembelow": "*omm", "chemleft": "m", "chemright": "m", "lewis": "mm", "Lewis": "mm",
        "chemmove": "*om", "molht": "m", "chemsign": "om", "chemrel": "om", "subscheme": "om",
    })
    ignored = dict(BASE_IGNORED, **{
        "setchemfig": "m", "resetchemfig": "", "setcharge": "m", "resetcharge": "",
        "definesubmol": "mom", "redefinesubmol": "mom", "definearrow": "mmm", "redefinearrow": "mmm",
        "setcompoundstyle": "m", "setarrowoffset": "m", "setatomsep": "m", "setbondoffset": "m",
        "setdoublesep": "m", "setangleincrement": "m", "setnodestyle": "m", "setbondstyle": "m",
        "setlewis": "m", "setlewisdist": "m", "setstacksep": "m", "hflipnext": "", "vflipnext": "",
        "enablebondjoin": "", "disablebondjoin": "", "setitemize": "m", "topsep": "", "parskip": "",
        "fboxsep": "", "fboxrule": "", "tableofcontents": "", "pagestyle": "m", "medbreak": "",
        "bigbreak": "", "smallbreak": "", "vphantom": "m", "hphantom": "m", "phantom": "m",
        "printatom": "", "chemskipalign": "", "null": "", "rlap": "m", "llap": "m",
        "CFhreacarrow": "", "setCFdelimiters": "m",
    })
    img_dir = IMGDIR_NAME
    table_class = "chemfig-table"

    def math_needs_image(self, content):
        return bool(re.search(r"\\(chem|boxednode|charge|Charge|lewis|Lewis|fbox|framebox)", content))

    # -- parts -----------------------------------------------------------------

    def cmd_part(self, k, e, out):
        args, e2 = read_args(self.s, e, "*om")
        title = self.inline(args[2])
        m = re.match(r"\s*\\label\{([^}]*)\}", self.s[e2:])
        if m:
            e2 += m.end()
            self.ctx.add_label(m.group(1), slug=self.slug, anchor="top", text=self.plain(args[2]),
                               kind="part")
        if self.page is not None and self.page.sections == 0:
            self.page.title = re.sub(r"<[^>]+>", "", title).strip()
            self.page.title_html = title
            out.append(("b", f'<h4 id="top"><span>{title}</span></h4>'))
        return e2

    # -- text macros ---------------------------------------------------------------

    def cmd_CF(self, k, e, out):
        out.append(("i", '<span class="chemfig-name">chem<i>fig</i></span>'))
        if self.s.startswith("{}", e):
            e += 2
        return e

    def cmd_TIKZ(self, k, e, out):
        return self.cmd_tikzname(k, e, out)

    def cmd_degres(self, k, e, out):
        out.append(("i", "°"))
        if self.s.startswith("{}", e):
            e += 2
        return e

    def cmd_chevrons(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="angle">&langle;</span><i>{self.inline(args[0])}</i>'
                         f'<span class="angle">&rangle;</span>'))
        return e2

    def cmd_textlangle(self, k, e, out):
        out.append(("i", "&langle;"))
        return e

    def cmd_textrangle(self, k, e, out):
        out.append(("i", "&rangle;"))
        return e

    def _teal(self, html):
        return f'<span class="textcolor" style="color: {TEAL}">{html}</span>'

    def cmd_CFkey(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", self._teal(f'<span class="texttt">{esc(self.raw(args[0]))}</span>')))
        return e2

    def cmd_CFval(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", self._teal(f"&langle;<i>{self.inline(args[0])}</i>&rangle;")))
        return e2

    def cmd_CFkv(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        out.append(("i", self._teal(f'<span class="texttt">{esc(self.raw(args[0]))}</span> = '
                                    f"&langle;<i>{self.inline(args[1])}</i>&rangle;")))
        return e2

    def _verbatim(self, e, out, meta):
        s = self.s
        if s[e] == "*":
            e += 1
        delim = s[e]
        end = s.find(delim, e + 1)
        text = esc(s[e + 1:end])
        if meta:
            text = re.sub(r"&lt;(.*?)&gt;", r'<span class="angle">&langle;</span><i>\1</i><span class="angle">&rangle;</span>', text)
        out.append(("i", f'<span class="verb">{text}</span>'))
        return end + 1

    def cmd_Verb(self, k, e, out):
        return self._verbatim(e, out, meta=True)

    def cmd_falseverb(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="verb">{esc(self.raw(args[0]))}</span>'))
        return e2

    cmd_boxedfalseverb = cmd_falseverb

    def cmd_CFver(self, k, e, out):
        out.append(("i", self.ctx.version))
        return e

    def cmd_paragraph(self, k, e, out):
        args, e2 = read_args(self.s, e, "*om")
        out.append(("b", f"<h6>{self.inline(args[2])}</h6>"))
        return e2

    # -- molecules and reactions ---------------------------------------------------

    def _image_until(self, k, end_cs, out):
        """\\schemestart ... \\schemestop and the like: one image."""
        stop = self.s.find(end_cs, k)
        if stop == -1:
            self.ctx.warn(f"missing {end_cs}")
            return k + 1
        e2 = stop + len(end_cs)
        if self.block_image_at(k):
            image_id = self.new_image(k, e2, "block")
            out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
        else:
            image_id = self.new_image(k, e2, "inline")
            out.append(("i", self.img_html(image_id, inline=True)))
        return e2

    def cmd_schemestart(self, k, e, out):
        return self._image_until(k, "\\schemestop", out)

    def cmd_hreac(self, k, e, out):
        return self._image_until(k, "\\endhreac", out)

    def cmd_exemple(self, k, e, out):
        """\\exemple[width]{title}|code|; \\exemple*: the code above the molecule."""
        s = self.s
        args, e2 = read_args(s, e, "*om")
        title = self.inline(args[2])
        while s[e2] in " \t":
            e2 += 1
        delim = s[e2]
        end = s.find(delim, e2 + 1)
        code = s[e2 + 1:end]
        image_id = self.new_image(k, None, "example")
        out.append(("b", '<figure class="example">'
                         f'<div class="example-image"><p>{self.img_html(image_id)}</p></div>'
                         + code_block(code, self.ctx, self.slug, title=title) + "</figure>"))
        return end + 1

    # -- tables ------------------------------------------------------------------

    env_tabular = Converter.env_html_table
    env_longtable = Converter.env_html_table
    # key tables: these macros print a key and its default value (read from chemfig.tex)
    table_row_macros = ("CFparam", "Chargeparam", "CFdelimparam")
    table_row_macros_partial = ("Chargeparam", "CFdelimparam")

    def table_row_macro(self, name, k):
        _, e = read_cs(self.s, k)
        args, e = read_args(self.s, e, "mm" if name == "CFparam" else "m")
        key = self.raw(args[0]).strip()
        family = {"CFparam": "chemfig", "Chargeparam": "charge", "CFdelimparam": "CFdelimiters"}[name]
        cells = [self._teal(f'<span class="texttt">{esc(key)}</span>'), self._default(family, key)]
        if name == "CFparam":
            cells.append(self.inline(args[1]))
        return cells, e

    def _default(self, family, key):
        value = self.ctx.defaults.get(family, {}).get(key, "")
        if value:
            return f'<span class="texttt">{esc(value)}</span>'
        return "&langle;<i>" + ("empty" if family == "chemfig" else "vide") + "</i>&rangle;"

    # -- change history ------------------------------------------------------------

    def cmd_CFchangelog(self, k, e, out):
        """\\CFchangelog{v1.82}{2026/09/19} \\item ... \\endCFchangelog (in French);
        !...! is verbatim inside."""
        args, e2 = read_args(self.s, e, "mm")
        stop = self.s.find("\\endCFchangelog", e2)
        version = self.raw(args[0]).lstrip("v")
        y, m, d = (self.raw(args[1]).split("/") + ["", "", ""])[:3]
        out.append(("b", f"<h6>Version {esc(version)} ({d}/{m}/{y})</h6>"))
        saved = self.short_verb_chars
        self.short_verb_chars = "|!"
        self.env_itemize(k, e2, stop, stop, out)
        self.short_verb_chars = saved
        return stop + len("\\endCFchangelog")


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def read_source(cid):
    return SOURCES[cid]


def convert_all(ctx):
    pages = []
    number = 0
    current_part = None
    for cid, slug, part, numbered in PAGES:
        if part != current_part:
            current_part, number = part, 0  # sections are numbered within their part
        if numbered:
            number += 1
        page = Page(cid, slug, part, str(number) if numbered else "")
        conv = ChemConverter(ctx, read_source(cid), slug, cid, page)
        page.body = conv.render(conv.items(0, len(conv.s)))
        page.captures = conv.captures
        pages.append(page)
    for label, part in PART_LABELS:
        first = next(p for p in pages if p.part == part)
        ctx.add_label(label, slug=first.slug, anchor="sec-1", text=dict(PARTS)[part], kind="part")
    return pages


def write_instrumented_tex(ctx, pages):
    os.makedirs(TEXDIR, exist_ok=True)
    for name in os.listdir(DOC):
        if not name.endswith(".pdf"):
            shutil.copy(os.path.join(DOC, name), TEXDIR)
    shutil.copy(os.path.join(SHARED, "texhtml", "tikzdev-capture.sty"), TEXDIR)
    shutil.copy(os.path.join(HERE, "chemhtml.sty"), TEXDIR)
    preamble, chunks, rest = split_chunks(TEXT)
    captures = {p.stem: p.captures for p in pages}
    body = []
    for i, (kind, title, start, stop) in enumerate(chunks):
        cid = f"c{i:02d}"
        chunk = TEXT[start:stop]
        body.append(instrument(chunk, captures[cid]) if cid in captures else chunk)
    preamble = preamble.replace("\\begin{document}", "\\usepackage{chemhtml}\n\\begin{document}", 1)
    with open(os.path.join(TEXDIR, "chemfig-html.tex"), "w", encoding="utf-8") as f:
        f.write(preamble + "".join(body) + rest)
    n = sum(1 for p in pages for c in p.captures if c[3] != "raw")
    print(f"Wrote instrumented sources to {TEXDIR} ({n} image fragments)")


MANUAL = Manual(
    package="chemfig",
    title="chemfig Manual",
    name_html='<span class="chemfig-name">chem<i>fig</i></span>',
    parts=PARTS,
    notice="""chemfig documentation:
Copyright 2010-2026 Christian Tellechea

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, version 1.3c.

tikz.dev:
Copyright 2021-2026 Dominik Peters
This file may be distributed and/or modified under the LaTeX Project Public License.""",
    footer_links=[("CTAN", "https://ctan.org/pkg/chemfig"),
                  ("Official PDF version", "https://mirrors.ctan.org/macros/generic/chemfig/chemfig-en.pdf"),
                  ("Source and license", "https://ctan.org/pkg/chemfig")],
    build_dir=BUILD,
    site_dir=SITE,
    img_dir=IMGDIR_NAME,
    home_title="chemfig Manual - Draw molecules with LaTeX",
)


def home_html(ctx, pages):
    sections = []
    for part_id, part_name in PARTS:
        lis = "".join(f'<li><a href="{p.slug}">{p.section_number + "&ensp;" if p.section_number else ""}'
                      f"{p.title_html}</a></li>" for p in pages if p.part == part_id)
        sections.append(f'<div class="home-toc-section"><h3><a href="{part_id}">{part_name}</a></h3><ul>{lis}</ul></div>')
    return f"""
<div class="manual-title-block">
<div class="manual-title"><span class="chemfig-name">chem<i>fig</i></span></div>
<div class="manual-version">A TeX package for drawing molecules, version {ctx.version} ({ctx.date})</div>
<div class="manual-authorship-explanation">Christian Tellechea</div>
<div class="manual-html-title">HTML version of the official documentation</div>
<div class="manual-html-explanation">This is an unofficial HTML rendering of the
<a href="https://ctan.org/pkg/chemfig">chemfig</a> manual, generated from its LaTeX sources.</div>
</div>
<div class="home-toc">{''.join(sections)}</div>
"""


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "html"
    ctx = Context()
    with open(os.path.join(DOC, "chemfig.tex"), encoding="utf-8") as f:
        src = f.read()
    ctx.version = re.search(r"\\def\\CFver\s*\{([^}]*)\}", src).group(1).strip()
    ctx.date = re.search(r"\\def\\CFdate\s*\{([^}]*)\}", src).group(1).strip()
    ctx.defaults = read_defaults()
    if mode == "html":
        load_images(ctx, os.path.join(BUILD, "images"))
    # pass 1: collect labels; pass 2: produce final HTML
    ctx.pass_no = 1
    convert_all(ctx)
    ctx.pass_no = 2
    ctx.warnings.clear()
    pages = convert_all(ctx)
    if mode == "tex":
        write_instrumented_tex(ctx, pages)
    else:
        write_site(MANUAL, ctx, pages, home_html)
        print(f"Wrote {len(pages)} pages to {SITE}")
    for msg, count in ctx.warnings.most_common(80):
        print(f"  warning ({count}x): {msg}")


if __name__ == "__main__":
    main()
