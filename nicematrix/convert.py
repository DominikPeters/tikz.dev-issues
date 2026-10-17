#!/usr/bin/env python3
"""Convert the nicematrix manual to HTML in the style of tikz.dev.

The manual (nicematrix.tex) is one file; every \\section becomes a page, the
introduction goes on the start page and the history of changes on a last page.
It is written with a few macros of its own:

* the piton environment Code shows a listing in which \\emph{...} highlights
  parts; with the key show-output, the environment also typesets the code (the
  manual's Code environment is patched to capture that output as an image).
  Without it, the output is usually typeset separately right after the
  listing; the converter then puts that image next to the listing.
* \\Definition{key} and \\DefinitionCommand{name} mark where a key or command
  is explained; they become anchors, and the names in the listings link there.

This script uses the shared converter in ../shared/texhtml (docs/converters.md).

Usage:
    convert.py tex     write the instrumented LaTeX sources to build/tex
    convert.py html    write the HTML pages (uses images if present)
"""

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, SHARED)
from texhtml.core import (  # noqa: E402
    EMPH_CLOSE, EMPH_OPEN, IGNORED as BASE_IGNORED, Context, Converter, Page, ParseError, code_block, esc,
    find_env_end, footnotes_html, instrument, load_images, match_brace, VERB_RE, read_args, read_cs, skip_ws, tex_to_text,
    xcolor_to_css,
)
from texhtml.site import Manual, write_site  # noqa: E402

# checkout of the nicematrix repository at the pinned commit (scripts/fetch.sh nicematrix)
UPSTREAM = os.environ.get("UPSTREAM", os.path.join(ROOT, ".upstream", "nicematrix"))
DOC = UPSTREAM
BUILD = os.path.join(HERE, "build")
TEXDIR = os.path.join(BUILD, "tex")
SITE = os.path.join(BUILD, "site", "nicematrix")
IMGDIR_NAME = "nicematrix-images"
MAIN = "nicematrix.tex"
JOB = "nicematrix-html"


def slugify(text):
    text = re.sub(r"^the\s+", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def heading_text(tex):
    tex = re.sub(r"\\texorpdfstring\{((?:[^{}]|\{[^{}]*\})*)\}\{[^{}]*\}", r"\1", tex)
    tex = tex.replace("\\textbackslash", "\\").replace("\\\\", "\\")
    tex = re.sub(r"\\(pkg|texttt|cls)\{([^}]*)\}", r"\2", tex)
    tex = re.sub(r"\\(?!\\)([A-Za-z]+)\s*", lambda m: "\\" + m.group(1) if m.group(1) not in ("protect",) else "", tex)
    return " ".join(tex.replace("{", "").replace("}", "").replace("``", "“").replace("''", "”").split())


# --------------------------------------------------------------------------
# The source: one file, split into chunks at \section
# --------------------------------------------------------------------------

SECTION_RE = re.compile(r"^\\section(\*?)\{", re.M)


def read_main():
    with open(os.path.join(DOC, MAIN), encoding="utf-8") as f:
        return f.read()


def split_chunks(text):
    """(preamble, [(stem, kind, title, start, end)], rest from \\cleardoublepage before the index).

    The first chunk is the introduction (from the abstract to the table of
    contents), the others start at a \\section."""
    intro = text.index("\\begin{abstract}")
    end = text.rindex("\\end{document}")
    index = text.rfind("\\cleardoublepage", 0, end)
    end = index if index != -1 else end
    marks = [m for m in SECTION_RE.finditer(text) if intro < m.start() < end]
    chunks = [("c00", "intro", "", intro, marks[0].start())]
    for i, m in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else end
        brace = m.end() - 1
        title = text[brace + 1:match_brace(text, brace)]
        chunks.append((f"c{i + 1:02d}", "starred" if m.group(1) else "section", title, m.start(), stop))
    return text[:intro], chunks, text[end:]


def read_structure():
    """Pages: (stem, slug, number) and their sources; the introduction separately."""
    text = read_main()
    _, chunks, _ = split_chunks(text)
    pages, sources, used = [], {}, set()
    number = 0
    for stem, kind, title, start, stop in chunks:
        sources[stem] = text[start:stop]
        if kind == "intro":
            continue
        slug = slugify(heading_text(title))
        if slug in used:
            slug = f"{slug}-{stem}"
        used.add(slug)
        if kind == "section":
            number += 1
        pages.append((stem, slug, str(number) if kind == "section" else ""))
    return pages, sources, text


PAGES, SOURCES, TEXT = read_structure() if os.path.isdir(DOC) else ([], {}, "")


# --------------------------------------------------------------------------
# The converter
# --------------------------------------------------------------------------

# Math that only LaTeX can typeset (the environments of nicematrix and their commands)
NICE_MATH = re.compile(r"Nice|\\Block|\\[CLVDI]dots|\\Hdotsfor|\\Vdotsfor|\\SubMatrix|\\CodeAfter|\\CodeBefore"
                       r"|\\[HV]brace|\\(Over|Under)Brace|\\diagbox|\\rotate|\\tikz|\\Hline|\\RowStyle")

# Keys documented by \Definition that are too common to link in every listing
# (they belong to TikZ, xcolor, ... as well)
UNLINKED_KEYS = {"name", "color", "code", "draw", "fill", "opacity", "width", "label", "command", "start", "end",
                 "tikz", "small", "empty", "offset", "shorten", "dotted", "dashed", "xshift", "yshift",
                 "transparent", "letter", "bold", "slim", "cols", "caption", "restart", "ccommand", "auto",
                 "borders", "margin", "multiplicity", "xoffset", "yoffset", "nocolor", "rowcolor", "tabularnote"}
UNLINKED_COMMANDS = {"left", "right", "line"}

PAGEREF = "\ue010"  # placeholder for \pageref, removed with its "p." (see clean_pagerefs)


class NiceConverter(Converter):
    """Converter for the macros of the nicematrix manual."""

    verbatim_envs = Converter.verbatim_envs | {"Code", "Verbatim", "BVerbatim"}
    transparent_envs = Converter.transparent_envs | {"scope", "ttfamily", "abstract"}
    ignored = dict(BASE_IGNORED, **{
        "NiceMatrixOptions": "m", "indexcommand": "m", "indexenv": "m", "UseName": "m", "pgfmathsetseed": "m",
        "interitem": "", "fvset": "m", "SetPitonStyle": "m", "PitonOptions": "m", "tableofcontents": "",
        "maketitle": "", "MakeShortVerb": "m", "makeindex": "", "skip": "", "footins": "", "hfuzz": "",
        "footnotemark": "o", "bigbreak": "",
    })
    img_dir = IMGDIR_NAME
    short_verb_chars = "|"
    env_tabular = Converter.env_html_table

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.code_only_end = None  # end of the last listing without output (see environment)

    # -- listings ----------------------------------------------------------------

    def code_html(self, code):
        """A listing of a Code environment: \\emph{...} highlighted, \\textsl{...} slanted."""
        out, i = [], 0
        while True:
            m = re.compile(r"\\(emph|textsl|myrlap)\s*\{").search(code, i)
            if not m:
                out.append(code[i:])
                break
            close = _code_brace(code, m.end() - 1)
            inner = code[m.end():close]
            out.append(code[i:m.start()])
            if m.group(1) == "emph":
                out.append(EMPH_OPEN + inner + EMPH_CLOSE)
            elif m.group(1) == "textsl":
                out.append("\ue002" + inner + "\ue003")
            else:
                out.append(inner)
            i = close + 1
        html = code_block("".join(out), self.ctx, self.slug)
        return (html.replace(EMPH_OPEN, '<span class="nm-emph">').replace(EMPH_CLOSE, "</span>")
                .replace("\ue002", "<i>").replace("\ue003", "</i>"))

    def env_Code(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "o")
        opts = {o.split("=")[0].strip() for o in (self.raw(args[0]) if args[0] else "").split(",")}
        code = self.code_html(self.s[a2:b])
        if "show-output" in opts:
            image_id = self.new_image(k, None, "example")
            out.append(("b", f'<figure class="example"><div class="example-image"><p>{self.img_html(image_id)}</p>'
                             f"</div>{code}</figure>"))
        elif "execute" in opts:
            out.append(("b", f'<figure class="example">{code}</figure>'))
        else:
            # the output, if any, is typeset right after the listing (see render)
            out.append(("b", f'<figure class="example">{code}</figure>', "code-only"))
            self.code_only_end = after

    def env_Verbatim(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "o")
        out.append(("b", '<figure class="example">' + code_block(self.s[a2:b], self.ctx, self.slug) + "</figure>"))

    env_BVerbatim = env_Verbatim

    def environment(self, k, e, b, out):
        s = self.s
        args, e2 = read_args(s, e, "m")
        name = self.raw(args[0])
        # a minipage right after a listing holds the listing's output: an image
        if name == "minipage" and self.code_only_end is not None and skip_ws(s, self.code_only_end) == k:
            try:
                _, after = find_env_end(s, e2, name, False)
            except ParseError as err:
                self.ctx.warn(str(err))
                return e2
            image_id = self.new_image(k, after, "block")
            out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
            return after
        if name == "table":  # a float with a tabular whose label is set by a key of nicematrix
            try:
                _, after = find_env_end(s, e2, name, False)
            except ParseError as err:
                self.ctx.warn(str(err))
                return e2
            m = re.search(r"\blabel\s*=\s*([\w:.-]+)", s[e2:after])
            anchor = ""
            if m:
                self.table_no = getattr(self.ctx, "table_no", 0) + 1 if self.ctx.pass_no == 1 else 0
                if self.ctx.pass_no == 1:
                    self.ctx.table_no = self.table_no
                    self.ctx.add_label(m.group(1), slug=self.slug, anchor=m.group(1), text=str(self.table_no),
                                       kind="table")
                anchor = f' id="{esc(m.group(1))}"'
            image_id = self.new_image(k, after, "block")
            out.append(("b", f'<div class="figure"{anchor}>{self.img_html(image_id)}</div>'))
            return after
        return super().environment(k, e, b, out)

    def render(self, items):
        """A listing without output followed by an image (the output typeset
        separately) become one example."""
        merged, i = [], 0
        while i < len(items):
            it = items[i]
            if len(it) == 3 and it[2] == "code-only":
                j = i + 1
                while j < len(items) and (items[j][0] == "p" or (items[j][0] == "i" and not items[j][1].strip())):
                    j += 1
                if j < len(items) and items[j][0] == "b" and items[j][1].startswith('<div class="figure">'):
                    img = items[j][1][len('<div class="figure">'):-len("</div>")]
                    merged.append(("b", it[1].replace('<figure class="example">', '<figure class="example">'
                                                      f'<div class="example-image"><p>{img}</p></div>', 1)))
                    i = j + 1
                    continue
            merged.append(it[:2])
            i += 1
        return super().render(merged)

    # -- math: the environments of nicematrix are images --------------------------

    def math_needs_image(self, content):
        return bool(NICE_MATH.search(content))

    def math(self, k, b, out):
        s = self.s
        if not s.startswith("$$", k):
            e = s.find("$", k + 1)
            if e != -1 and self.math_needs_image(s[k + 1:e]) and self.block_image_at(k):
                image_id = self.new_image(k, e + 1, "block")
                out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
                return e + 1
        return super().math(k, b, out)

    def command(self, k, b, out):
        s = self.s
        if s.startswith("\\[", k):
            end = s.find("\\]", k)
            if end != -1 and self.math_needs_image(s[k + 2:end]):
                image_id = self.new_image(k, end + 2, "block")
                out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
                return end + 2
        return super().command(k, b, out)

    # -- definitions -----------------------------------------------------------------

    def _definition(self, e, out, command=False):
        args, e2 = read_args(self.s, e, "m")
        text = self.plain(args[0]).strip()
        if command:
            text = "\\" + text
        if text.startswith("{") and text.endswith("}"):
            kind, name = "env", text[1:-1]
        elif text.startswith("\\"):
            kind, name = "cmd", text[1:]
        else:
            kind, name = "key", text
        anchor = f"{kind}-" + re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
        if self.page is not None:
            used = self.page.__dict__.setdefault("def_anchors", set())
            base, n = anchor, 2
            while anchor in used:
                anchor, n = f"{base}-{n}", n + 1
            used.add(anchor)
        label = f"nm-{kind}:{name}"
        if self.ctx.pass_no == 1 and label not in self.ctx.labels:
            self.ctx.add_label(label, slug=self.slug, anchor=anchor, text=text, kind=kind)
            if kind == "key" and len(name) > 2 and name not in UNLINKED_KEYS:
                self.ctx.known_keys.setdefault(name, label)
            elif kind == "cmd" and name not in UNLINKED_COMMANDS:
                self.ctx.known_commands.setdefault(name, label)
            elif kind == "env":
                self.ctx.known_envs.setdefault(name, label)
        out.append(("i", f'<span class="nm-def" id="{esc(anchor)}">{esc(text)}</span>'))
        return e2

    def cmd_Definition(self, k, e, out):
        return self._definition(e, out)

    def cmd_DefinitionCommand(self, k, e, out):
        return self._definition(e, out, command=True)

    # -- text macros --------------------------------------------------------------------

    def cmd_pkg(self, k, e, out):
        return self._wrap(e, out, '<span class="sffamily">', "</span>")

    cmd_cls = cmd_pkg

    def cmd_textsl(self, k, e, out):
        return self._wrap(e, out, "<i>", "</i>")

    def cmd_texorpdfstring(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        out.append(("i", self.inline(args[0])))
        return e2

    def cmd_nolinkurl(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        url = self.raw(args[0]).strip()
        href = url if "://" in url else url.replace("https:", "https://", 1)
        out.append(("i", f'<a href="{esc(href)}">{esc(url)}</a>'))
        return e2

    def cmd_colorbox(self, k, e, out):
        """\\colorbox{yellow!50}{\\bfseries New 7.9}: a text badge, not an image"""
        args, e2 = read_args(self.s, e, "mm")
        inner_src = self.raw(args[1])
        if re.search(r"\$|\\tikz|\\begin|Nice|\\Block", inner_src):
            return self.inline_image(k, e, "colorbox", out)
        inner = "".join(x[1] for x in self.group(*args[1]) if x[0] != "p")
        color = xcolor_to_css(self.raw(args[0]))
        out.append(("i", f'<span class="nm-badge" style="background-color: {color}">{inner.strip()}</span>'))
        return e2

    def cmd_footnote(self, k, e, out):
        """With VerbatimFootnotes, |...| in a footnote may contain unbalanced braces."""
        a = skip_ws(self.s, e)
        end = _brace_short_verb(self.s, a)
        if self.page is not None:
            self.page.footnotes.append(self.render(self.items(a + 1, end)))
            n = len(self.page.footnotes)
            out.append(("i", f'<sup class="footnotemark"><a href="#footnote-{n}" id="footnotemark-{n}">{n}</a></sup>'))
        return end + 1

    def cmd_tikz(self, k, e, out):
        """\tikz[options]{...} or \tikz[options] path ;"""
        s = self.s
        _, j = read_args(s, e, "o")
        j = skip_ws(s, j)
        end = match_brace(s, j) + 1 if s.startswith("{", j) else s.index(";", j) + 1
        if self.block_image_at(k):
            image_id = self.new_image(k, end, "block")
            out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
        else:
            image_id = self.new_image(k, end, "inline")
            out.append(("i", self.img_html(image_id, inline=True)))
        return end

    def cmd_newline(self, k, e, out):
        out.append(("i", "<br />"))
        return e

    def cmd_enskip(self, k, e, out):
        out.append(("i", "\u2002"))
        return e

    def cmd_pageref(self, k, e, out):
        args, e2 = read_args(self.s, e, "*m")
        out.append(("i", PAGEREF))
        return e2

    def cmd_emphase(self, k, e, out):
        return e

    # sections: \section is a page; starred headings are not numbered
    def cmd_section(self, k, e, out):
        return self.heading(k, e, out, 1)

    def cmd_subsection(self, k, e, out):
        return self.heading(k, e, out, 2)

    def cmd_subsubsection(self, k, e, out):
        return self.heading(k, e, out, 3)

    def heading(self, k, e, out, level, title=None):
        args, e2 = read_args(self.s, e, "*om")
        if not args[0]:
            return super().heading(k, e, out, level, title)
        title = self.inline(args[2])
        anchor = "sec-" + slugify(re.sub(r"<[^>]+>", "", title))
        tag = {1: "h4", 2: "h5", 3: "h6"}[level]
        out.append(("b", f'<{tag} id="{anchor}"><span>{title}</span><a class="anchor-link" href="#{anchor}">&para;</a>'
                         f"</{tag}>"))
        if level == 1:
            self.page.title = re.sub(r"<[^>]+>", "", title).strip()
            self.page.title_html = title
        else:
            self.page.toc.append(("tocsubsection" if level == 2 else "tocsubsubsection", anchor, title))
        return e2


def _brace_short_verb(s, k):
    """The brace closing s[k], skipping |...| (short verbatim) and comments."""
    depth, i = 0, k
    while i < len(s):
        c = s[i]
        if c == "\\":
            m = VERB_RE.match(s, i)
            i = s.find(m.group(1), m.end()) + 1 if m else i + 2
            continue
        if c == "|":
            close = s.find("|", i + 1)
            if close != -1 and "\n\n" not in s[i:close]:
                i = close + 1
                continue
        if c == "%":
            i = s.find("\n", i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ParseError(f"unbalanced brace: {s[k:k + 60]!r}")


def _code_brace(code, k):
    """The brace closing code[k] in a listing (where % is not a comment)."""
    depth, i = 0, k
    while i < len(code):
        c = code[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ParseError(f"unbalanced brace in listing: {code[k:k + 60]!r}")


def clean_pagerefs(html_text):
    """"cf. 4.2, p. 17" makes no sense in HTML: drop the page references."""
    html_text = re.sub(r",?\s*(?:p\.|page)(?:\s|\u00a0|&nbsp;)*" + PAGEREF, "", html_text)
    return html_text.replace(PAGEREF, "")


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def convert_all(ctx):
    pages = []
    for stem, slug, number in PAGES:
        page = Page(stem, slug, None, number)
        conv = NiceConverter(ctx, SOURCES[stem], slug, stem, page)
        page.body = clean_pagerefs(conv.render(conv.items(0, len(conv.s))))
        page.footnotes = [clean_pagerefs(fn) for fn in page.footnotes]
        page.captures = conv.captures
        pages.append(page)
    # the introduction, for the start page
    intro = Page("c00", "index", None, "")
    conv = NiceConverter(ctx, SOURCES["c00"], "index", "c00", intro)
    intro.body = clean_pagerefs(conv.render(conv.items(0, len(conv.s))))
    intro.captures = conv.captures
    ctx.intro = intro
    return pages


def write_instrumented_tex(ctx, pages):
    os.makedirs(TEXDIR, exist_ok=True)
    for name in os.listdir(DOC):
        if os.path.isfile(os.path.join(DOC, name)):
            shutil.copy(os.path.join(DOC, name), TEXDIR)
    shutil.copy(os.path.join(SHARED, "texhtml", "tikzdev-capture.sty"), TEXDIR)
    # nicematrix.sty of this version
    subprocess.run(["tex", "-interaction=batchmode", "nicematrix.ins"], cwd=TEXDIR, check=True, capture_output=True)
    preamble, chunks, rest = split_chunks(TEXT)
    captures = {p.stem: p.captures for p in pages}
    captures["c00"] = ctx.intro.captures
    body = [instrument(TEXT[start:stop], captures[stem]) for stem, _, _, start, stop in chunks]
    preamble = patch_code_environment(preamble)
    preamble = preamble.replace("\\begin{document}", "\\usepackage{tikzdev-capture}\n\\begin{document}", 1)
    with open(os.path.join(TEXDIR, JOB + ".tex"), "w", encoding="utf-8") as f:
        f.write(preamble + "".join(body) + rest)
    n = sum(1 for p in pages + [ctx.intro] for c in p.captures if c[3] != "raw")
    print(f"Wrote instrumented sources to {TEXDIR} ({n} image fragments)")


def patch_code_environment(preamble):
    """Capture the output that the Code environment typesets with show-output."""
    output = "\\lua_now:n { tex.print(piton.get_last_code():explode(string.char(10)))}"
    start = preamble.index("\\bool_if:NT \\l__pantigny_show_output_bool")
    head, tail = preamble[:start], preamble[start:]
    if tail.count(output) != 2:
        raise SystemExit("the definition of the Code environment has changed; adapt patch_code_environment")
    return head + tail.replace(output, "\\HTMLexamplebegin" + output + "\\HTMLexampleend")


MANUAL = Manual(
    package="nicematrix",
    title="nicematrix Manual",
    name_html='The <span class="sffamily">nicematrix</span> package',
    parts=[],
    notice="""nicematrix documentation:
Copyright (C) 2018-2026 by F. Pantigny

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, either version 1.3 of this license or (at your
option) any later version.

tikz.dev:
Copyright 2021-2026 Dominik Peters
This file may be distributed and/or modified under the LaTeX Project Public License.""",
    footer_links=[("CTAN", "https://ctan.org/pkg/nicematrix"),
                  ("Official PDF version", "https://mirrors.ctan.org/macros/latex/contrib/nicematrix/nicematrix.pdf"),
                  ("Source and license", "https://github.com/fpantigny/nicematrix")],
    build_dir=BUILD,
    site_dir=SITE,
    img_dir=IMGDIR_NAME,
    home_title="nicematrix Manual - Enhanced arrays with the help of PGF/TikZ",
)


def home_html(ctx, pages):
    lis = "".join(f'<li><a href="{p.slug}">{p.section_number + "&ensp;" if p.section_number else ""}'
                  f"{p.title_html}</a></li>" for p in pages)
    intro = ctx.intro
    return f"""
<div class="manual-title-block">
<div class="manual-title">The package <span class="sffamily">nicematrix</span></div>
<div class="manual-version">Version {ctx.version} ({ctx.date})</div>
<div class="manual-authorship-explanation">F. Pantigny</div>
<div class="manual-html-title">HTML version of the official documentation</div>
<div class="manual-html-explanation">This is an unofficial HTML rendering of the
<a href="https://ctan.org/pkg/nicematrix">nicematrix</a> manual, generated from its LaTeX sources.</div>
</div>
<div class="nm-intro">{intro.body}{footnotes_html(intro)}</div>
<div class="home-toc"><div class="home-toc-section"><h3>Contents</h3><ul>{lis}</ul></div></div>
"""


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "html"
    ctx = Context()
    with open(os.path.join(DOC, "nicematrix-code.dtx"), encoding="utf-8") as f:
        src = f.read()
    ctx.version = re.search(r"\\def\\myfileversion\{([^}]*)\}", src).group(1)
    ctx.date = re.search(r"\\def\\myfiledate\{([^}]*)\}", src).group(1)
    if mode == "html":
        load_images(ctx, os.path.join(BUILD, "images"))
    # pass 1: collect labels and definitions; pass 2: produce final HTML
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
