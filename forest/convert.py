#!/usr/bin/env python3
"""Convert the forest manual to HTML in the style of tikz.dev.

The manual (forest-doc.tex) is one file; every \\subsection becomes a page and
every \\section a part. It is written with forest's own documentation macros:

* \\index{option>content} and friends (\\indexdef, \\indexex) print the name of
  an option, style, step, ... and link it to its definition; \\indexitem in a
  syntax environment defines an entry. How a name is printed depends on its
  category (and short forms like \\index{content} must be resolved), so instead
  of reimplementing forest-index, the LaTeX run logs the printed form of every
  \\index call (forhtml.sty); this script converts those forms to HTML. Before
  the first LaTeX run, a simplified form is used.
* forestexample shows the code next to the tree it draws; the tree is captured
  as an image (forhtml.sty), as are forest environments in running text.

This script uses the shared converter in ../shared/texhtml (docs/converters.md).

Usage:
    convert.py tex     write the instrumented LaTeX sources to build/tex
    convert.py html    write the HTML pages (uses images and printed forms if present)
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
    DEF_COLOR, IGNORED as BASE_IGNORED, Context, Converter, Page, code_block, esc, instrument,
    load_images, match_brace, parse_bib, read_args, read_cs, split_items, tex_to_text,
)
from texhtml.site import Manual, sort_citations, write_site  # noqa: E402
from home import contents, find_examples, showcase, title_box  # noqa: E402

# checkout of the forest repository at the pinned commit (scripts/fetch.sh forest)
UPSTREAM = os.environ.get("UPSTREAM", os.path.join(ROOT, ".upstream", "forest"))
DOC = UPSTREAM
BUILD = os.path.join(HERE, "build")
TEXDIR = os.path.join(BUILD, "tex")
SITE = os.path.join(BUILD, "site", "forest")
IMGDIR_NAME = "forest-images"
MAIN = "forest-doc.tex"
JOB = "forest-doc-html"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def heading_text(tex):
    tex = re.sub(r"\\(FoRest|foRest|TikZ|PGF);", lambda m: {"TikZ": "TikZ", "PGF": "PGF"}.get(m.group(1), "forest"), tex)
    tex = tex.replace("\\protect", "")
    return " ".join(tex_to_text(tex).replace("{", "").replace("}", "").split())


# --------------------------------------------------------------------------
# The source: one file, split into chunks at \section and \subsection
# --------------------------------------------------------------------------

def read_main():
    """forest-doc.tex, with the documentation of the .dtx files it \\DocInput's
    (libraries, forest-index) unwrapped into it."""
    with open(os.path.join(DOC, MAIN), encoding="utf-8") as f:
        text = f.read()
    return re.sub(r"\\DocInput\{([^}]*)\}", lambda m: unwrap_dtx(m.group(1)), text)


def unwrap_dtx(name):
    """The documentation of a .dtx file as LaTeX: comment characters removed,
    docstrip guards dropped, macrocode blocks as listings."""
    with open(os.path.join(DOC, name), encoding="utf-8") as f:
        lines = f.read().split("\n")
    out = []
    in_code = False
    for line in lines:
        if in_code:
            if re.match(r"%    \\end\{macrocode\}", line):
                out.append("\\end{lstlisting}")
                in_code = False
            elif not line.startswith("%<"):
                out.append(line)
            continue
        if re.match(r"%    \\begin\{macrocode\}", line):
            out.append("\\begin{lstlisting}[gobble=0]")
            in_code = True
        elif line.startswith("%<"):
            continue
        elif line.startswith("%"):
            doc = line[2:] if line.startswith("% ") else line[1:]
            if doc.strip() == "\\endinput":  # ends the .dtx file, not the manual
                break
            out.append(doc)
        else:
            out.append(line)
    return "\n".join(out)


HEADING_RE = re.compile(r"^\\(section|subsection|librarysection)\{", re.M)


def split_chunks(text):
    """(preamble up to the first section, [(kind, title, start, end)], rest from \\end{document})."""
    first = HEADING_RE.search(text, text.index("\\begin{document}")).start()
    end = text.index("\\end{document}")
    marks = [(m.start(), m.group(1)) for m in HEADING_RE.finditer(text) if first <= m.start() < end
             and not _commented(text, m.start())]
    chunks = []
    for i, (pos, kind) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else end
        brace = text.index("{", pos)
        chunks.append((kind, text[brace + 1:match_brace(text, brace)], pos, stop))
    return text[:first], chunks, text[end:]


def _commented(text, pos):
    line = text[text.rfind("\n", 0, pos) + 1:pos]
    return "%" in line


def read_structure():
    """Parts (sections) and pages: (chunk id, page name, part id, number)."""
    text = read_main()
    _, chunks, _ = split_chunks(text)
    parts, pages, sources = [], [], {}
    used = set()
    part = None
    section_no = subsection_no = 0
    for i, (kind, title, start, stop) in enumerate(chunks):
        name = heading_text(title)
        body = text[start:stop]
        cid = f"c{i:02d}"
        if kind == "section":
            section_no += 1
            subsection_no = 0
            part = "part-" + slugify(name)
            parts.append((part, name))
            rest = re.sub(r"^\\section\{.*?\}(\s*\\label\{[^}]*\})?", "", body, flags=re.S)
            if not re.sub(r"%[^\n]*", "", rest).strip():
                continue
            number = str(section_no)
        else:
            subsection_no += 1
            number = f"{section_no}.{subsection_no}"
            if kind == "librarysection":
                name = "library " + name
        slug = slugify(name)
        if slug in used:
            slug = slugify(dict(parts)[part]) + "-" + slug
        used.add(slug)
        sources[cid] = body
        pages.append((cid, slug, part, number))
    return parts, pages, sources, text


PARTS, PAGES, SOURCES, TEXT = read_structure() if os.path.isdir(DOC) else ([], [], {}, "")


def read_printed_forms():
    """The printed forms of the \\index calls logged by forhtml.sty: {id: TeX}."""
    path = os.path.join(TEXDIR, JOB + ".htmlindex")
    forms = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                ident, _, code = line.rstrip("\n").partition(" ")
                forms[ident] = code  # the last one wins (the text, not the table of contents)
    return forms


def target_anchor(target):
    """HTML id for a forest-index hypertarget like "option>calign"."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "-", target.replace(">", ":").replace(" ", "-"))


# --------------------------------------------------------------------------
# The converter
# --------------------------------------------------------------------------

INDEX_CALL = re.compile(r"\\(index|indexdef|indexex)(?![A-Za-z])")


class ForestConverter(Converter):
    """Converter for the macros of the forest manual."""

    verbatim_envs = Converter.verbatim_envs | {"forestexample", "lstlisting"}
    transparent_envs = Converter.transparent_envs | {"multicols", "compactitem"}
    # \printbig...list: trees of all nodewalk steps / processor instructions, drawn by the manual
    inline_image_commands = Converter.inline_image_commands | {"Forest", "Repeat", "printbigbadforlist",
                                                               "printbigbadprocesslist"}
    inline_image_specs = dict(Converter.inline_image_specs, Forest="*om", Repeat="mm", printbigbadforlist="m",
                              printbigbadprocesslist="m")
    ignored = dict(BASE_IGNORED, **{
        "indexset": "*om", "forestset": "m", "bracketset": "m", "itemnosep": "o",
        "useforestlibrary": "*om", "forestapplylibrarydefaults": "m", "lstset": "m",
        "DeleteShortVerb": "m", "MakeShortVerb": "m", "EnableCrossrefs": "", "tikzexternaldisable": "",
        "maketitle": "", "tableofcontents": "", "forest@memoize": "m", "CheckSum": "m",
        "lstdefinelanguage": "omom", "pstyle": "", "forestexampleimport": "",
        "marginpar": "om", "PrintIndex": "", "PrintChanges": "", "medbreak": "", "bigbreak": "",
    })
    img_dir = IMGDIR_NAME
    short_verb_chars = "|"

    # in the converter of a printed form (see print_form): links and targets only
    in_print_form = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.index_counter = 0

    # -- the printed forms of \index ---------------------------------------------

    def next_index_id(self, k):
        """Announce an identifier for the \\index call at s[k] (logged by forhtml.sty)."""
        if self.stem is None or self.in_print_form:
            return None
        self.index_counter += 1
        ident = f"{self.stem}-i{self.index_counter}"
        self.captures.append((k, None, f"\\HTMLindexnext{{{ident}}}", "raw"))
        return ident

    def print_form(self, code):
        sub = type(self)(self.ctx, code, self.slug, None, self.page)
        sub.in_print_form = True
        return sub.inline((0, len(code)))

    def fallback_form(self, key):
        """Before the first LaTeX run: the last part of the key, linked if it is a full key."""
        name = key.split(">")[-1]
        name = re.sub(r"^\s*([^=]*?)\s*=.*$", r"\1", name, flags=re.S) or name
        html = f'<span class="texttt">{self.inline_text(name)}</span>'
        if ">" in key:
            href = self.ctx.href("idx:" + key.strip(), self.slug)
            if href:
                html = f'<a href="{esc(href)}">{html}</a>'
        return html

    def _index(self, k, e, out):
        """\\index(default)[options]>{key}"""
        if self.s.startswith("(", e):
            e = self.s.index(")", e) + 1
        args, e2 = read_args(self.s, e, "o")
        opts = self.raw(args[0]) if args[0] else ""
        if self.s.startswith(">", e2):
            e2 += 1
        args2, e3 = read_args(self.s, e2, "m")
        key = self.raw(args2[0])
        ident = self.next_index_id(k)
        if "not print" in opts:
            return e3
        code = self.ctx.printed.get(ident) if ident else None
        out.append(("i", self.print_form(code) if code else self.fallback_form(key)))
        return e3

    def cmd_index(self, k, e, out):
        return self._index(k, e, out)

    cmd_indexdef = cmd_index
    cmd_indexex = cmd_index

    def cmd_hyperlink(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        target = self.raw(args[0]).strip()
        inner = self.inline(args[1])
        href = self.ctx.href("idx:" + target, self.slug)
        out.append(("i", f'<a href="{esc(href)}">{inner}</a>' if href else inner))
        return e2

    def cmd_hypertarget(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        target = self.raw(args[0]).strip()
        anchor = target_anchor(target)
        if self.page is not None:
            # a key defined twice on a page: links go to the first definition
            used = self.page.__dict__.setdefault("index_anchors", set())
            base, n = anchor, 2
            while anchor in used:
                anchor, n = f"{base}-{n}", n + 1
            used.add(anchor)
            self.ctx.add_label("idx:" + target, slug=self.slug, anchor=anchor, text=target, kind="index")
        # the definition itself, not a link to its index entry
        inner = re.sub(r"^<a href=\"[^\"]*\">(.*)</a>$", r"\1", self.inline(args[1]), flags=re.S)
        out.append(("i", f'<span id="{esc(anchor)}">{inner}</span>'))
        return e2

    def cmd_textcolor(self, k, e, out):
        if not self.in_print_form:
            return super().cmd_textcolor(k, e, out)
        args, e2 = read_args(self.s, e, "mm")  # links are blue, definitions red: done by the page style
        out.append(("i", self.inline(args[1])))
        return e2

    def cmd_char(self, k, e, out):
        j = e
        while j < len(self.s) and self.s[j] == " ":
            j += 1
        if self.s.startswith("\\escapechar", j):
            out.append(("i", "\\"))
            return j + len("\\escapechar")
        return super().cmd_char(k, e, out)

    def cmd_indexpipe(self, k, e, out):
        out.append(("i", "|"))
        return e

    def cmd_space(self, k, e, out):
        out.append(("i", " "))
        return e

    # -- entries: \indexitem in syntax environments ---------------------------------

    SIGNATURE_CS = {"meta", "marg", "oarg", "OR", "keyname", "texttt", "index", "indexex", "cmdname",
                    "dots", "ldots", "textbraceleft", "textbraceright", "space", "emph", "alternative"}

    def _signature_end(self, a, b):
        """End of the signature after an \\indexitem: verbatim, \\meta{...} and the like,
        punctuation; it stops at the first ordinary word (the description)."""
        s = self.s
        i = a
        end = a
        while i < b:
            c = s[i]
            if c == "\n":
                break
            if c in " \t":
                i += 1
                continue
            if c == "|":
                j = s.find("|", i + 1)
                if j == -1 or j > b:
                    break
                i = end = j + 1
                continue
            if c == "\\":
                name, j = read_cs(s, i)
                if name not in self.SIGNATURE_CS:
                    break
                while j < b and s[j] in "{[":
                    j = match_brace(s, j, s[j], "}" if s[j] == "{" else "]") + 1
                i = end = j
                continue
            if c in "=[](){},.:+-*'" or (c == "$" and s.find("$", i + 1) != -1):
                if c == "$":
                    j = s.find("$", i + 1) + 1
                else:
                    j = i + 1
                i = end = j
                continue
            break
        return end

    def entry(self, headline, category, default, a, b, anchor_hint, out):
        notes = []
        if category:
            notes.append(category)
        if default:
            notes.append(f"default <kbd>{default}</kbd>")
        note = f'<span class="hl-default">({", ".join(notes)})</span>' if notes else ""
        m = re.search(r'id="([^"]+)"', headline)
        anchor = m.group(1) if m else anchor_hint
        link = f'<a class="anchor-link" href="#{esc(anchor)}">&para;</a>' if anchor else ""
        body = self.render(self.items(a, b))
        out.append(("b", '<div class="manualentry"><ul class="list" style="list-style-type: none">'
                         f'<div class="entryheadline"><li><p><span class="hl-def">{headline}</span>{note}{link}</p></li></div>'
                         + body + "</ul></div>"))

    def _item_parts(self, code, key):
        """Key, category and default from the printed form \\item[,default,category]{key}."""
        if code and code.lstrip().startswith("\\item"):
            sub = type(self)(self.ctx, code, self.slug, None, self.page)
            sub.in_print_form = True
            # \item[,default,category]{key}; the default may be "[" (bracket keys)
            m = re.match(r"\s*\\item\s*\[(.*?)\]\s*\{", code, re.S)
            if m:
                brace = m.end() - 1
                key_html = sub.inline((brace + 1, match_brace(code, brace)))
                fields = [f.strip() for f in _split_commas(m.group(1))] + ["", "", ""]
                default = fields[1]
                if default.startswith("{") and default.endswith("}"):
                    default = default[1:-1]
                return self._red(key_html), sub.inline_text(fields[2]), esc(default)
            return self.print_form(code), "", ""
        if code:
            return self._red(self.print_form(code)), "", ""
        category = key.split(">")[0].split("=")[0].strip() if ">" in key else ""
        return self._red(self.fallback_form(key)), category, ""

    @staticmethod
    def _red(html):
        return f'<span class="textcolor" style="color: {DEF_COLOR}">{html}</span>'

    def env_syntax(self, k, a, b, after, out):
        s = self.s
        first = s.find("\\indexitem", a, b)
        while first != -1 and _commented(s, first):
            first = s.find("\\indexitem", first + 1, b)
        if first == -1:
            out.extend(self.items(a, b))
            return
        out.extend(self.items(a, first))
        for x, y in split_items(s, first, b, cmd="\\indexitem", verbatim_envs=self.verbatim_envs,
                                short_verb=self.short_verb_chars):
            k0 = x - len("\\indexitem")
            e = x
            if s.startswith("(", e):
                e = s.index(")", e) + 1
            args, e = read_args(s, e, "o")
            if s.startswith(">", e):
                e += 1
            args, e = read_args(s, e, "m")
            key = self.raw(args[0])
            ident = self.next_index_id(k0)
            code = self.ctx.printed.get(ident) if ident else None
            headline, category, default = self._item_parts(code, key)
            sig_end = self._signature_end(e, y)
            signature = self.inline((e, sig_end)) if sig_end > e else ""
            if signature:
                headline += f"<kbd>{signature}</kbd>" if "<" not in signature else signature
            self.entry(headline, category, default, sig_end, y, target_anchor(key), out)

    def env_indexitemprocessinstruction(self, k, a, b, after, out):
        """\\begin{indexitemprocessinstruction}(default)[options]{char}[form](modifiers){first line}*{signature}"""
        s = self.s
        e = a
        if s.startswith("(", e):
            e = s.index(")", e) + 1
        args, e = read_args(s, e, "om")
        char = self.raw(args[1])
        form_args, e = read_args(s, e, "o")
        modifiers = ""
        e2 = e
        while e2 < len(s) and s[e2] in " \t\n":
            e2 += 1
        if s.startswith("(", e2):
            close = s.index(")", e2)
            modifiers = self.inline((e2 + 1, close))
            e = close + 1
        first, e = read_args(s, e, "*m")
        sig, e = read_args(s, e, "m")
        ident = self.next_index_id(k)
        code = self.ctx.printed.get(ident) if ident else None
        headline, _, _ = self._item_parts(code, "processor>" + char)
        if not code:
            headline = f'<span class="texttt">{esc(self.raw(form_args[0]) if form_args[0] else char)}</span>'
        headline += f'<span class="texttt">{modifiers}</span> {self.inline(first[1])}'
        if not first[0] and sig[0] is not None:
            cells = [c.strip() for c in self.raw(sig[0]).split("&")] + ["", "", "", ""]
            conv = [self.inline_text(c) for c in cells[:4]]
            headline += (f'&emsp;<span class="processor-signature">{conv[0]} 👁 {conv[1]} &rarr; '
                         f"{conv[2]} 👁 {conv[3]}</span>")
        self.entry(headline, "processor", "", e, b, target_anchor("processor>" + char), out)

    # -- text macros -----------------------------------------------------------------

    def _logo(self, e, out, html):
        out.append(("i", html))
        return e + 1 if self.s.startswith(";", e) else e

    def cmd_FoRest(self, k, e, out):
        return self._logo(e, out, '<span class="forest-name">Forest</span>')

    cmd_foRest = cmd_FoRest

    def cmd_TikZ(self, k, e, out):
        return self._logo(e, out, '<span class="tikzname">TikZ</span>')

    def cmd_PGF(self, k, e, out):
        return self._logo(e, out, "PGF")

    def cmd_keyname(self, k, e, out):
        return self._wrap(e, out, '<span class="texttt">', "</span>")

    def cmd_cmdname(self, k, e, out):
        return self._wrap(e, out, '<span class="texttt">\\', "</span>")

    def cmd_alternative(self, k, e, out):
        """\\alternative{a,b,c}: a choice of values"""
        args, e2 = read_args(self.s, e, "m")
        choices = [esc(c.strip()) for c in _split_commas(self.raw(args[0]))]
        out.append(("i", '<span class="texttt">' + "|".join(choices) + "</span>"))
        return e2

    def cmd_entry(self, k, e, out):
        """\\entry{x} in forest-index's documentation: “x”"""
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f"“{self.inline(args[0])}”"))
        return e2

    def cmd_spaces(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        n = self.raw(args[0]).strip()
        out.append(("i", "&nbsp;" * (int(n) if n.isdigit() else 1)))
        return e2

    def cmd_rstyle(self, k, e, out):
        return e

    def cmd_OR(self, k, e, out):
        out.append(("i", " | "))
        return e

    def cmd_reflibrary(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        name = self.raw(args[0])
        out.append(("i", self._label_link(f"sec:library-{name}", f'<span class="texttt">{esc(name)}</span>')))
        return e2

    def cmd_hyperrefnocolor(self, k, e, out):
        args, e2 = read_args(self.s, e, "om")
        label = self.raw(args[0]) if args[0] else ""
        out.append(("i", self._label_link(label, self.inline(args[1])) if label else self.inline(args[1])))
        return e2

    cmd_hyperref = cmd_hyperrefnocolor

    def cmd_citep(self, k, e, out):
        """natbib: \\citep[pre][post]{keys}, \\citep[post]{keys}"""
        args, e2 = read_args(self.s, e, "oom")
        pre, post = (args[0], args[1]) if args[1] else (None, args[0])
        keys = [x.strip() for x in self.raw(args[2]).split(",")]
        links = []
        for key in keys:
            if key not in self.ctx.cited:
                self.ctx.cited.append(key)
            links.append(f'<a href="references#{esc(key)}">{esc(self.ctx.cite_labels.get(key, "?"))}</a>')
        text = (self.inline(pre) + " " if pre else "") + ", ".join(links) + (", " + self.inline(post) if post else "")
        out.append(("i", "[" + text + "]"))
        return e2

    cmd_citet = cmd_citep

    def cmd_eye(self, k, e, out):
        out.append(("i", "👁"))
        return e

    def cmd_greaterthan(self, k, e, out):
        out.append(("i", "&gt;"))
        return e

    def cmd_DescribeMacro(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="texttt">{esc(self.raw(args[0]))}</span>'))
        return e2

    def cmd_librarysection(self, k, e, out):
        """\\librarysection{name}: \\subsection{\\texttt{name}}\\label{sec:library-name}"""
        args, e2 = read_args(self.s, e, "m")
        name = self.raw(args[0])
        e3 = self.heading(k, e2, out, 1, title=f'<span class="texttt">{esc(name)}</span>')
        self.ctx.add_label(f"sec:library-{name}", slug=self.slug, anchor="sec-" + self.page.top_number,
                           text=self.page.top_number, kind="section")
        return e3

    # sections: \section is a part, \subsection a page
    def cmd_section(self, k, e, out):
        return self.heading(k, e, out, 1)

    def cmd_subsection(self, k, e, out):
        return self.heading(k, e, out, 1)

    def cmd_subsubsection(self, k, e, out):
        return self.heading(k, e, out, 2)

    def cmd_paragraph(self, k, e, out):
        return self.heading(k, e, out, 3)

    # -- examples and listings ---------------------------------------------------------

    def env_forestexample(self, k, a, b, after, out):
        s = self.s
        opts, code_start = "", a
        j = a
        while j < b and s[j] in " \t":
            j += 1
        if j < b and s[j] == "[":
            e = match_brace(s, j, "[", "]")
            opts, code_start = s[j + 1:e], e + 1
        code = s[code_start:b]
        parts = []
        layout = re.search(r"layout\s*=\s*([\w ]+)", opts)
        layout = layout.group(1).strip() if layout else "tree on left"
        anchor = ""
        if "no label" not in opts and not re.search(r"counter\s*=\s*\{\s*\}", opts) and layout != "export":
            self.ctx.example_no += 1
            number = str(self.ctx.example_no)
            m = re.search(r"label\s*=\s*\{?([\w:*.-]+)", opts)
            if m:
                self.ctx.add_label(m.group(1), slug=self.slug, anchor=m.group(1), text=number, kind="example")
                anchor = f' id="{esc(m.group(1))}"'
            parts.append(f'<div class="example-number">({number})</div>')
        if layout != "only code":
            image_id = self.new_image(k, None, "example")
            parts.append(f'<div class="example-image"><p>{self.img_html(image_id)}</p></div>')
        if layout != "only tree":
            parts.append(code_block(code, self.ctx, self.slug))
        cls = "example" + (" example-vertical" if layout in ("tree on top", "tree on bottom") else "")
        out.append(("b", f'<figure class="{cls}"{anchor}>' + "".join(parts) + "</figure>"))

    def env_lstlisting(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "o")
        out.append(("b", '<figure class="example">' + code_block(self.s[a2:b], self.ctx, self.slug) + "</figure>"))

    def cmd_lstinputregion(self, k, e, out):
        """\\lstinputregion[opts]{file}{region}: a marked region of a source file."""
        args, e2 = read_args(self.s, e, "omm")
        path = os.path.join(DOC, self.raw(args[1]).strip())
        region = self.raw(args[2]).strip()
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            m = re.search(r"%%% begin listing region: " + re.escape(region) + r"\n(.*?)\n[ \t]*%%% end listing region: "
                          + re.escape(region), text, re.S)
            code = m.group(1) if m else ""
        except OSError:
            code = ""
        if code:
            out.append(("b", '<figure class="example">' + code_block(code, self.ctx, self.slug) + "</figure>"))
        return e2

    def cmd_lstinline(self, k, e, out):
        s = self.s
        args, e = read_args(s, e, "o")
        delim = s[e]
        end = s.find("}" if delim == "{" else delim, e + 1)
        out.append(("i", f'<span class="verb">{esc(s[e + 1:end])}</span>'))
        return end + 1

    def env_advise(self, k, a, b, after, out):
        lis = [f"<li>{self.render(self.items(x, y))}</li>" for x, y in
               split_items(self.s, a, b, verbatim_envs=self.verbatim_envs)]
        out.append(("b", '<ul class="advise">' + "".join(lis) + "</ul>"))

    env_arguments = Converter.env_enumerate
    env_compactitem = Converter.env_itemize


def _split_commas(text):
    parts, depth, start = [], 0, 0
    for i, c in enumerate(text):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def convert_all(ctx):
    ctx.example_no = 0
    pages = []
    for cid, slug, part, number in PAGES:
        page = Page(cid, slug, part, number)
        conv = ForestConverter(ctx, SOURCES[cid], slug, cid, page)
        page.body = conv.render(conv.items(0, len(conv.s)))
        page.captures = conv.captures
        pages.append(page)
    return pages


def write_instrumented_tex(ctx, pages):
    os.makedirs(TEXDIR, exist_ok=True)
    for name in os.listdir(DOC):
        if os.path.isfile(os.path.join(DOC, name)):
            shutil.copy(os.path.join(DOC, name), TEXDIR)
    shutil.copy(os.path.join(SHARED, "texhtml", "tikzdev-capture.sty"), TEXDIR)
    shutil.copy(os.path.join(HERE, "forhtml.sty"), TEXDIR)
    for ins in ("forest.ins", "forest-doc.ins"):  # forest.sty, forest-index.sty, ... of this version
        subprocess.run(["tex", "-interaction=batchmode", ins], cwd=TEXDIR, check=True, capture_output=True)
    preamble, chunks, rest = split_chunks(TEXT)
    captures = {p.stem: p.captures for p in pages}
    body = []
    for i, (kind, title, start, stop) in enumerate(chunks):
        cid = f"c{i:02d}"
        chunk = TEXT[start:stop]
        body.append(instrument(chunk, captures[cid]) if cid in captures else chunk)
    # LuaLaTeX: forest's documentation code uses \pdfstrcmp; no externalization
    # (it would compile every tree in a separate pdflatex run)
    preamble = "\\RequirePackage{pdftexcmds}\\makeatletter\\let\\pdfstrcmp\\pdf@strcmp\\makeatother\n" + preamble
    start = preamble.index("\\IfFileExists{forest-doc.tex-externalize.tex}")
    stop = preamble.index("\\tikzset{\n  external/prefix")
    preamble = preamble[:start] + preamble[stop:]
    preamble = preamble.replace("\\usepackage{forest-doc}", "\\usepackage{forest-doc}\n\\usepackage{forhtml}", 1)
    preamble = preamble.replace("\\begin{document}", "\\tikzexternaldisable\n\\begin{document}", 1)
    with open(os.path.join(TEXDIR, JOB + ".tex"), "w", encoding="utf-8") as f:
        f.write(preamble + "".join(body) + rest)
    n = sum(1 for p in pages for c in p.captures if c[3] != "raw")
    print(f"Wrote instrumented sources to {TEXDIR} ({n} image fragments)")


MANUAL = Manual(
    package="forest",
    title="forest Manual",
    name_html='<span class="forest-name">Forest</span>',
    parts=PARTS,
    notice="""forest documentation:
Copyright (c) 2012-2017 Saso Zivanovic

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, either version 1.3 of this license or (at your
option) any later version.

tikz.dev:
Copyright 2021-2026 Dominik Peters
This file may be distributed and/or modified under the LaTeX Project Public License.""",
    footer_links=[("CTAN", "https://ctan.org/pkg/forest"),
                  ("Official PDF version", "https://mirrors.ctan.org/graphics/pgf/contrib/forest/forest-doc.pdf"),
                  ("Source and license", "https://github.com/sasozivanovic/forest")],
    build_dir=BUILD,
    site_dir=SITE,
    img_dir=IMGDIR_NAME,
    home_title="forest Manual - Drawing linguistic trees with PGF/TikZ",
)



# examples whose pictures the start page shows: (page, fragment of the code without whitespace)
SHOWCASE = [
    ('decision-tree.html', '\\forestset{declaretoks={'),
    ('library-linguistics.html', "t}[VP[DP[John]][V'[V,dra"),
    ('decorating-the-tree.html', '\\begin{forest}[XP[specif'),
]

def home_html(ctx, pages):
    groups = [(part_name, part_id, "", [(p.section_number, p.title_html, p.slug) for p in pages if p.part == part_id])
              for part_id, part_name in PARTS]
    box = title_box('<span class="forest-name">Forest</span>',
                    f"A PGF/TikZ-based package for drawing linguistic trees, version {ctx.version.lstrip('v')}",
                    "Author of the forest manual: Sašo Živanović.", "https://github.com/sasozivanovic/forest")
    return f"""
{box}
{showcase(find_examples({p.slug + '.html': p.body for p in pages}, SHOWCASE))}
{contents(groups)}
"""


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "html"
    ctx = Context()
    with open(os.path.join(DOC, "forest.dtx"), encoding="utf-8") as f:
        m = re.search(r"\\ProvidesPackage\{forest\}\s*\[([\d/]+)\s+(v[\d.]+)", f.read())
    ctx.version = m.group(2) if m else ""
    ctx.date = m.group(1) if m else ""
    ctx.bib = parse_bib(os.path.join(DOC, "tex.bib")) if os.path.exists(os.path.join(DOC, "tex.bib")) else {}
    ctx.printed = read_printed_forms() if mode == "html" else {}
    if mode == "html":
        load_images(ctx, os.path.join(BUILD, "images"))
    # pass 1: collect labels and definitions; pass 2: produce final HTML
    ctx.pass_no = 1
    convert_all(ctx)
    sort_citations(ctx)
    ctx.pass_no = 2
    ctx.warnings.clear()
    pages = convert_all(ctx)
    if mode == "tex":
        write_instrumented_tex(ctx, pages)
    else:
        write_site(MANUAL, ctx, pages, home_html)
        print(f"Wrote {len(pages)} pages to {SITE} ({len(ctx.printed)} printed index forms)")
    for msg, count in ctx.warnings.most_common(80):
        print(f"  warning ({count}x): {msg}")


if __name__ == "__main__":
    main()
