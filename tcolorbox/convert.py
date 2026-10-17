#!/usr/bin/env python3
"""Convert the tcolorbox manual to HTML in the style of tikz.dev.

Instead of running the manual through lwarp, this script parses the LaTeX
sources of the manual directly (with the shared converter in
../shared/texhtml). It understands the macros of the `documentation` library
of tcolorbox (docCommand, docTcbKey, dispExample, \\refKey, ...) and maps them
onto the HTML structure produced by the tikz.dev pipeline, so that the shared
tikz.dev style.css and pgfmanual.js apply.

Everything that is genuinely visual (the compiled part of examples, boxes in
running text, pictures, tables, ...) becomes an image. For that, the script
writes an instrumented copy of the manual into build/tex in which each such
fragment is marked with an identifier (see texhtml/capture.sty and
tcbhtml.sty). Compiling that copy with LuaLaTeX produces one extra PDF page
per fragment, which build.sh crops and converts.

Usage:
    convert.py tex     write the instrumented LaTeX sources
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
    DEF_COLOR, LATEX_LOGO, Context, Converter, code_block, convert_pages, esc, instrument,
    load_images, match_brace, parse_bib, pretty_id, read_args, skip_ws, split_kv,
)
from texhtml.site import Manual, sort_citations, write_site  # noqa: E402

# checkout of the tcolorbox repository at the pinned commit (scripts/fetch.sh tcolorbox)
UPSTREAM = os.environ.get("UPSTREAM", os.path.join(ROOT, ".upstream", "tcolorbox"))
DOC = os.path.join(UPSTREAM, "doc", "latex", "tcolorbox")
BUILD = os.path.join(HERE, "build")
TEXDIR = os.path.join(BUILD, "tex")
SITE = os.path.join(BUILD, "site", "tcolorbox")
IMGDIR_NAME = "tcolorbox-images"

PARTS = [
    ("core", "The Core Package"),
    ("libraries", "Libraries"),
    ("appendix", "Appendix"),
]

# (source file stem, url slug, part)
CHAPTERS = [
    ("intro", "introduction", "core"),
    ("quickref", "quick-reference", "core"),
    ("coremacros", "box-creation", "core"),
    ("coreoptions", "option-keys", "core"),
    ("initoptions", "initialization-options", "core"),
    ("sidebyside", "side-by-side", "core"),
    ("verbatim", "verbatim", "core"),
    ("recording", "recording", "core"),
    ("technical", "technical-overview", "core"),
    ("skins", "library-skins", "libraries"),
    ("skincatalog", "skin-catalog", "libraries"),
    ("graphics", "image-boxes", "libraries"),
    ("filling", "tikz-auxiliary-macros", "libraries"),
    ("beamer", "beamer", "libraries"),
    ("vignette", "library-vignette", "libraries"),
    ("raster", "library-raster", "libraries"),
    ("listings", "library-listings", "libraries"),
    ("theorems", "library-theorems", "libraries"),
    ("breakable", "library-breakable", "libraries"),
    ("magazine", "library-magazine", "libraries"),
    ("poster", "library-poster", "libraries"),
    ("fitting", "library-fitting", "libraries"),
    ("hooks", "library-hooks", "libraries"),
    ("xparse", "library-xparse", "libraries"),
    ("external", "library-external", "libraries"),
    ("documentation", "library-documentation", "libraries"),
    ("tagging", "tagging", "appendix"),
    ("picturecredits", "picture-credits", "appendix"),
]

# Environments whose body is verbatim (never parsed as LaTeX).
VERBATIM_ENVS = {
    "dispExample", "dispExample*", "exdispExample", "exdispExample*",
    "dispListing", "dispListing*", "tcblisting", "tcbverbatimwrite",
    "tcbwritetemp", "tcboutputlisting", "fulldocumentlisting", "verbatim",
    "lstlisting", "minted", "tcbexternal", "extcolorbox", "extikzpicture",
    "mycbox", "texexp", "texexptitled", "texercise", "exercise",
}
# Verbatim environments that only write files (no output in the document).
SILENT_VERBATIM_ENVS = {"tcbverbatimwrite", "tcbwritetemp", "tcboutputlisting"}

# Environments whose content is converted to HTML (everything else that is
# unknown becomes an image).
TRANSPARENT_ENVS = {"multicols", "minipage", "flushleft", "flushright", "document",
                    "small", "footnotesize"}

INLINE_IMAGE_COMMANDS = {
    "tcbox", "tcboxfit", "tcboxverb", "tcboxmath", "tcbhighmath",
    "tcbincludegraphics", "tcbincludepdf", "includegraphics", "tcbuselistingtext",
    "tcbuselistinglisting", "tcbusetemplisting", "tcbinputlisting", "tcbusetemp",
    "tcbuselistingtext", "tikz", "diabox", "mybox", "useboxarray", "usetcboxarray",
    "consumeboxarray", "consumetcboxarray",
    "doShadingExample", "tcbline", "fbox", "colorbox", "fcolorbox", "tcbvignette",
}
# argument specs for the inline image commands (to find their extent)
INLINE_IMAGE_SPECS = {
    "tcbox": "*om", "tcboxfit": "om", "tcboxverb": "om", "tcboxmath": "om",
    "tcbhighmath": "om", "tcbincludegraphics": "om", "tcbincludepdf": "om",
    "includegraphics": "*om", "tcbuselistingtext": "", "tcbuselistinglisting": "",
    "tcbusetemplisting": "o", "tcbinputlisting": "m", "tcbusetemp": "", "tikz": "o",
    "diabox": "omm", "mybox": "om", "useboxarray": "omm", "usetcboxarray": "omm",
    "consumeboxarray": "omm", "consumetcboxarray": "omm", "tcbinputrecords": "om",
    "tcblistof": "om", "doShadingExample": "mm", "tcbline": "*", "fbox": "m",
    "colorbox": "mm", "fcolorbox": "mmm", "tcbvignette": "m",
}

DEFINITION_RE = re.compile(r"\\(?:new|renew|provide|Declare|New|Renew|Provide)[A-Za-z]*|\\tcbset\b|\\def\b"
                           r"|\\tcbuselibrary|\\usetikzlibrary|\\begin\{(?:figure|table)|\\tcb(?:start|stop)recording"
                           r"|\\tcblistof|\\tcbinputrecords|\\(?:sub)*section")

# Commands that produce nothing in HTML; value = argument spec to skip.
IGNORED = {
    "index": "m", "clearpage": "", "newpage": "", "cleardoublepage": "",
    "noindent": "", "indent": "", "smallskip": "", "medskip": "", "bigskip": "",
    "vspace": "*m", "hspace": "*m", "vskip": "", "hfill": "", "vfill": "", "hfil": "",
    "tcbset": "m", "tcbuselibrary": "m", "usetikzlibrary": "m", "makeatletter": "",
    "makeatother": "", "par": "", "relax": "", "enlargethispage": "*m", "nopagebreak": "o",
    "pagebreak": "o", "linebreak": "o", "nolinebreak": "o", "allowbreak": "",
    "phantomsection": "", "strut": "", "centering": "", "raggedright": "", "raggedleft": "",
    "addtocontents": "mm", "addcontentsline": "mmm", "setlength": "mm", "addtolength": "mm",
    "tcbsetforeverylayer": "m", "pgfkeys": "m", "pgfkeysalso": "m", "tikzset": "m",
    "newtcolorbox": "omoom", "renewtcolorbox": "omoom", "newtcbox": "omoom",
    "renewtcbox": "omoom", "newtcblisting": "omoom", "newtcbinputlisting": "omoom",
    "newtcbtheorem": "ommmm", "NewTcbTheorem": "ommmm", "tcbstartrecording": "o",
    "tcbstoprecording": "", "tcbrecord": "m", "newcounter": "mo", "setcounter": "mm",
    "stepcounter": "m", "newlength": "m", "newboxarray": "m", "boxarrayclear": "o",
    "boxarrayreset": "o", "definecolor": "mmm", "colorlet": "mm",
    "tcbhighmath": "om", "lstdefinestyle": "mm", "lstset": "m", "inputpreamble": "m",
    "tcbEXTERNALIZE": "", "printbibliography": "o", "printindex": "", "appendix": "",
    "mbox": "", "ignorespaces": "", "unskip": "", "kill": "", "nobreak": "",
    "bookmarksetup": "m", "hypersetup": "m", "AddToHook": "mom", "zcsetup": "m",
    "zcRefTypeSetup": "mm", "tcbsetmanagedlayer": "m", "tcbmakedocSubKey": "omm",
    "tcbmakedocSubKeys": "omm", "pgfplotsset": "m", "tcbAUXmkdir": "m", "@starttoc": "m",
    "lstMakeShortInline": "m", "colFade": "m", "tcbposterset": "m", "thispagestyle": "m",
    "pagestyle": "m", "selectlanguage": "m", "BeginAccSupp": "m", "EndAccSupp": "m",
    "nocite": "m", "displaystyle": "", "normalfont": "", "upshape": "", "mdseries": "",
}
for _name in ("DeclareTColorBox", "NewTColorBox", "RenewTColorBox", "ProvideTColorBox",
              "DeclareTCBox", "NewTCBox", "RenewTCBox", "ProvideTCBox",
              "DeclareTCBListing", "NewTCBListing", "RenewTCBListing", "ProvideTCBListing",
              "DeclareTCBInputListing", "NewTCBInputListing", "DeclareTCBoxFit", "NewTCBoxFit"):
    IGNORED[_name] = "ommm"
for _name in ("DeclareTotalTColorBox", "NewTotalTColorBox", "RenewTotalTColorBox",
              "ProvideTotalTColorBox", "DeclareTotalTCBox", "NewTotalTCBox",
              "DeclareTotalTCBoxFit", "NewTotalTCBoxFit"):
    IGNORED[_name] = "ommmm"
for _name in ("NewDocumentCommand", "RenewDocumentCommand", "DeclareDocumentCommand",
              "NewDocumentEnvironment", "RenewDocumentEnvironment"):
    IGNORED[_name] = "mmm"
for _name in ("newcommand", "renewcommand", "providecommand", "newrobustcmd"):
    IGNORED[_name] = "*mo" + "om"
for _name in ("newenvironment", "renewenvironment"):
    IGNORED[_name] = "*moomm"


def toc_title(page):
    """Section title for tables of contents (library badges become plain text)."""
    return re.sub(r'<span class="mylib">(.*?)</span>', r"\1", page.title_html)


MANUAL = Manual(
    package="tcolorbox",
    title="tcolorbox Manual",
    name_html="The tcolorbox package",
    parts=PARTS,
    notice="""The tcolorbox package documentation:
Copyright (c) 2006-2026 by Prof. Dr. Dr. Thomas F. Sturm

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, either version 1.3 of this license or (at your
option) any later version.

tikz.dev:
Copyright 2021-2026 Dominik Peters
This file may be distributed and/or modified under the LaTeX Project Public License.""",
    footer_links=[("License", "https://www.latex-project.org/lppl/"),
                  ("CTAN", "https://ctan.org/pkg/tcolorbox"),
                  ("Official PDF version", "https://mirrors.ctan.org/macros/latex/contrib/tcolorbox/tcolorbox.pdf"),
                  ("tcolorbox on GitHub", "https://github.com/T-F-S/tcolorbox")],
    build_dir=BUILD,
    site_dir=SITE,
    img_dir=IMGDIR_NAME,
    home_title="tcolorbox Manual - Complete Online Documentation",
    toc_title=toc_title,
)


class TcbConverter(Converter):
    """Converter for the macros of tcolorbox's documentation library."""

    verbatim_envs = VERBATIM_ENVS
    silent_verbatim_envs = SILENT_VERBATIM_ENVS
    transparent_envs = TRANSPARENT_ENVS
    inline_image_commands = INLINE_IMAGE_COMMANDS
    inline_image_specs = INLINE_IMAGE_SPECS
    ignored = IGNORED
    img_dir = IMGDIR_NAME

    def math_needs_image(self, content):
        return "tcb" in content or "\\boxed" in content

    def cmd_tcbusetemp(self, k, e, out):
        if DEFINITION_RE.search(self.last_temp):
            # the code defines things which must stay visible afterwards, so it
            # cannot run inside a capture group; it gets no image
            return e
        return self.inline_image(k, e, "tcbusetemp", out)

    def env_tcbwritetemp(self, k, a, b, after, out):
        self.last_temp = self.s[a:b]

    def cmd_version(self, k, e, out):
        out.append(("i", self.ctx.version))
        return e

    def cmd_datum(self, k, e, out):
        out.append(("i", self.ctx.date))
        return e

    def cmd_mylib(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="mylib">{self.inline(args[0])}</span>'))
        return e2

    cmd_tcbinterruptdraftmode = Converter.cmd_bgroup
    cmd_tcbcontinuedraftmode = Converter.cmd_bgroup


    def cmd_colOpt(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="colopt">{self.inline(args[0])}</span>'))
        return e2

    def cmd_colDef(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="textcolor" style="color: {DEF_COLOR}">{self.inline(args[0])}</span>'))
        return e2

    def _docvalue(self, k, e, out, prefix="", cls="docvalue"):
        args, e2 = read_args(self.s, e, "*om")
        out.append(("i", f'<span class="texttt {cls}">{esc(prefix)}{self.inline(args[2])}</span>'))
        return e2

    def cmd_docValue(self, k, e, out):
        return self._docvalue(k, e, out)

    def cmd_docColor(self, k, e, out):
        return self._docvalue(k, e, out)

    def cmd_docCounter(self, k, e, out):
        return self._docvalue(k, e, out)

    def cmd_docLength(self, k, e, out):
        return self._docvalue(k, e, out, prefix="\\")

    def cmd_docFading(self, k, e, out):
        return self._docvalue(k, e, out)

    def cmd_docAuxCommand(self, k, e, out):
        return self._docvalue(k, e, out, prefix="\\", cls="docdef")

    def cmd_docAuxEnvironment(self, k, e, out):
        return self._docvalue(k, e, out, cls="docdef")

    def cmd_docAuxKey(self, k, e, out):
        args, e2 = read_args(self.s, e, "*oom")
        path = self.raw(args[1]) if args[1] else ""
        name = self.inline(args[3])
        prefix = f"/{path}/" if path else ""
        out.append(("i", f'<span class="texttt docdef">{esc(prefix)}{name}</span>'))
        return e2

    def cmd_tcbdocmarginnote(self, k, e, out):
        args, e2 = read_args(self.s, e, "om")
        out.append(("i", f'<span class="marginnote">{self.inline(args[1])}</span>'))
        return e2

    def cmd_tcbdocnew(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="docnew">New: {self.inline(args[0])}</span>'))
        return e2

    def cmd_tcbdocupdated(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="docupdated">Updated: {self.inline(args[0])}</span>'))
        return e2

    def cmd_tcbdocdescNoDefaultInit(self, k, e, out):
        out.append(("i", "no default, initially unset"))
        return e

    def cmd_tcbdocdescInitEmpty(self, k, e, out):
        out.append(("i", "no default, initially empty"))
        return e

    def cmd_tcbdocdescInit(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f"no default, initially <kbd>{self.inline(args[0])}</kbd>"))
        return e2

    def cmd_tcbdocdescDefault(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f"default <kbd>{self.inline(args[0])}</kbd>, initially unset"))
        return e2

    def cmd_tcbdocdescDefaultInitEmpty(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f"default <kbd>{self.inline(args[0])}</kbd>, initially empty"))
        return e2

    def cmd_tcbdocdescDefaultInit(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        out.append(("i", f"default <kbd>{self.inline(args[0])}</kbd>, initially <kbd>{self.inline(args[1])}</kbd>"))
        return e2

    def cmd_docKeyChoices(self, k, e, out):
        args, e2 = read_args(self.s, e, "*m")
        choices = []
        for key, val in split_kv(self.s, *args[1]):
            if val is None:
                choices.append(self.inline_text(key))
            else:
                choices.append(self.inline(val))
        sep = '<span class="choicesep">|</span>'
        html_ = "<kbd>=</kbd>" + sep.join(choices)
        if args[0]:
            html_ = f'<span class="colopt">{html_}</span>'
        out.append(("i", html_))
        return e2

    # references
    def _ref_doc(self, k, e, out, kind):
        args, e2 = read_args(self.s, e, "*m")
        name = self.raw(args[1]).strip()
        label = f"{kind}:{name}"
        info = self.ctx.labels.get(label)
        if kind == "com":
            text = "\\" + name
        elif info is not None:
            text = info["text"]
        else:
            text = name
        href = self.ctx.href(label, self.slug)
        if href is None and self.ctx.pass_no == 2:
            self.ctx.warn(f"unresolved {label}")
        inner = f'<span class="texttt">{esc(text)}</span>'
        if href:
            inner = f'<a href="{esc(href)}">{inner}</a>'
        out.append(("i", inner))
        return e2

    def cmd_refCom(self, k, e, out):
        return self._ref_doc(k, e, out, "com")

    def cmd_refEnv(self, k, e, out):
        return self._ref_doc(k, e, out, "env")

    def cmd_refKey(self, k, e, out):
        return self._ref_doc(k, e, out, "key")

    def cmd_refPathOperation(self, k, e, out):
        return self._ref_doc(k, e, out, "path")

    def cmd_refSkin(self, k, e, out):
        return self._ref_doc(k, e, out, "skin")

    def cmd_refAux(self, k, e, out):
        return self._wrap(e, out, '<span class="texttt">', "</span>")

    def cmd_refAuxcs(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="texttt">\\{self.inline(args[0])}</span>'))
        return e2

    def cmd_refPkg(self, k, e, out):
        args, e2 = read_args(self.s, e, "om")
        name = self.raw(args[1])
        target = self.raw(args[0]) if args[0] else name
        out.append(("i", f'<a href="https://ctan.org/pkg/{esc(target)}"><span class="texttt">{esc(name)}</span></a>'))
        return e2


    def cmd_inputpreamblelisting(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        code = self.ctx.preamble_listings.get(self.raw(args[0]).strip(), "")
        out.append(("b", '<figure class="example">'
                         + code_block(code, self.ctx, self.slug, title="Definition in the preamble:")
                         + "</figure>"))
        return e2

    def cmd_DeclareTotalTColorBox(self, k, e, out):
        return self._xparse_define(e, 2)

    cmd_NewTotalTColorBox = cmd_DeclareTotalTColorBox
    cmd_DeclareTotalTCBox = cmd_DeclareTotalTColorBox
    cmd_NewTotalTCBox = cmd_DeclareTotalTColorBox

    def cmd_DeclareTCBox(self, k, e, out):
        args, e2 = read_args(self.s, e, "omm")
        name = self.raw(args[1]).strip().lstrip("\\")
        self.user_macros[name] = "om"
        _, e3 = read_args(self.s, e2, "m")
        return e3

    cmd_NewTCBox = cmd_DeclareTCBox

    def cmd_newtcbox(self, k, e, out):
        args, e2 = read_args(self.s, e, "omoom")
        name = self.raw(args[1]).strip().lstrip("\\")
        n = int(self.raw(args[2])) if args[2] else 0
        self.user_macros[name] = "o" + "m" * max(n, 1)
        return e2

    cmd_renewtcbox = cmd_newtcbox

    def env_marker(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "o")
        # outer div carries the shadow, inner div the clipped (dog-eared) shape
        out.append(("b", f'<div class="marker"><div class="marker-box">{self.render(self.items(a2, b))}</div></div>'))

    def env_deprecated(self, k, a, b, after, out):
        out.append(("b", f'<div class="deprecated">{self.render(self.items(a, b))}</div>'))

    # examples
    def _example(self, k, code_start, b, out, opts=None, listing=False):
        code = self.s[code_start:b]
        self.last_temp = code
        options = self.raw(opts) if opts else ""
        listing_only = "listing only" in options or listing
        anchors = ""
        for m in re.finditer(r"(?:phantom)?label=\{?([\w:.-]+)", options):
            if self.page is not None:
                self.ctx.add_label(m.group(1), slug=self.slug, anchor=m.group(1),
                                   text=self.page.current_number, kind="label")
                anchors += f'<a id="{esc(m.group(1))}"></a>'
        text_only = "text only" in options
        parts = []
        if not listing_only:
            image_id = self.new_image(k, None, "example")
            parts.append(f'<div class="example-image"><p>{self.img_html(image_id)}</p></div>')
        if not text_only:
            parts.append(code_block(code, self.ctx, self.slug))
        out.append(("b", anchors + '<figure class="example">' + "".join(parts) + "</figure>"))

    def env_dispExample(self, k, a, b, after, out):
        self._example(k, a, b, out)

    def env_dispExample_(self, k, a, b, after, out):
        # dispExample*{options}
        args, a2 = read_args(self.s, a, "m")
        self._example(k, a2, b, out, args[0])

    def env_exdispExample(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "om")
        self._example(k, a2, b, out)

    def env_exdispExample_(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "omm")
        self._example(k, a2, b, out, args[2])

    def env_dispListing(self, k, a, b, after, out):
        self.last_temp = self.s[a:b]
        out.append(("b", '<figure class="example">' + code_block(self.s[a:b], self.ctx, self.slug) + "</figure>"))

    def env_dispListing_(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "m")
        self._example(k, a2, b, out, args[0], listing=True)

    def env_tcblisting(self, k, a, b, after, out):
        opt_open = self.s.index("{", a)
        opt_close = match_brace(self.s, opt_open)
        if "pdf comment" in self.s[opt_open:opt_close]:
            self._compiled_listing(k, opt_close, opt_close + 1, b, after, out)
            return
        image_id = self.new_image(k, after, "block")
        out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))

    def env_fulldocumentlisting(self, k, a, b, after, out):
        opt_open = self.s.index("{", a)
        opt_close = match_brace(self.s, opt_open)
        self._compiled_listing(k, opt_close, opt_close + 1, b, after, out)

    def _compiled_listing(self, k, opt_end, code_start, b, after, out):
        """A listing whose compiled result (pdf comment) is shown below it:
        the code becomes text; only the compiled pages are captured as image."""
        self.captures.append((opt_end, None, ",comment only", "raw"))
        image_id = self.new_image(k, after, "block")
        code = self.s[code_start:b].lstrip("\n")
        out.append(("b", '<figure class="example">'
                    f'<div class="example-image"><p>{self.img_html(image_id)}</p></div>'
                    + code_block(code, self.ctx, self.slug) + "</figure>"))

    # documentation entries
    def env_docCommand(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "omm")
        self.doc_entry("command", [{"name": args[1], "parameter": args[2]}], args[0], a2, b, out)

    env_docCommand_ = env_docCommand

    def env_docEnvironment(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "omm")
        self.doc_entry("environment", [{"name": args[1], "parameter": args[2]}], args[0], a2, b, out)

    env_docEnvironment_ = env_docEnvironment

    def env_docPathOperation(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "omm")
        self.doc_entry("path", [{"name": args[1], "parameter": args[2]}], args[0], a2, b, out)

    def _doc_key(self, k, a, b, out, subpath):
        args, a2 = read_args(self.s, a, "oommm")
        extra_path = self.raw(args[0]).strip() if args[0] else ""
        path = subpath if not extra_path else (f"{subpath}/{extra_path}" if subpath else extra_path)
        heads = [{"name": args[2], "parameter": args[3], "description": args[4], "keypath": path}]
        self.doc_entry("key", heads, args[1], a2, b, out)

    def _doc_keys(self, k, a, b, out, subpath, kind="key"):
        args, a2 = read_args(self.s, a, "om")
        heads = []
        common = self.kv_dict(args[0]) if args[0] else {}
        for hk, hv in split_kv(self.s, *args[1]):
            # each entry is {doc name=..., ...}; split_kv returns it as a key with braces
            pass
        # parse the list of brace groups
        s = self.s
        i = args[1][0]
        while True:
            i = skip_ws(s, i)
            if i >= args[1][1]:
                break
            if s[i] == ",":
                i += 1
                continue
            if s[i] != "{":
                break
            j = match_brace(s, i)
            d = dict(common)
            d.update(self.kv_dict((i + 1, j)))
            head = self._head_from_kv(d)
            if kind == "key":
                extra = head.get("keypath_raw")
                head["keypath"] = (subpath if not extra else (f"{subpath}/{extra}" if subpath else extra))
            heads.append(head)
            i = j + 1
        if not heads:
            head = self._head_from_kv(dict(common))
            if kind == "key":
                extra = head.get("keypath_raw")
                head["keypath"] = (subpath if not extra else (f"{subpath}/{extra}" if subpath else extra))
            heads.append(head)
        self.doc_entry(kind, heads, None, a2, b, out, common_kv=common)


    def _head_from_kv(self, d):
        head = {}
        if "doc name" in d:
            head["name"] = d["doc name"]
        if "doc parameter" in d:
            head["parameter"] = d["doc parameter"]
        for variant, fmt in (("doc parameter eq meta", "=\\meta{%s}"), ("doc parameter eq marg", "=\\marg{%s}"),
                             ("doc parameter marg", "\\marg{%s}"), ("doc parameter oarg", "\\oarg{%s}"),
                             ("doc parameter eq", "=%s")):
            if variant in d:
                head["parameter_text"] = fmt % self.raw(d[variant])
        if "doc description" in d:
            head["description"] = d["doc description"]
        for variant, fmt in (("doc description init", "\\tcbdocdescInit{%s}"),
                             ("doc description default", "\\tcbdocdescDefault{%s}"),
                             ("doc description default init empty", "\\tcbdocdescDefaultInitEmpty{%s}"),
                             ("doc description default init", "\\tcbdocdescDefaultInit%s"),
                             ("doc description init empty", "\\tcbdocdescInitEmpty%s"),
                             ("doc description no default init", "\\tcbdocdescNoDefaultInit%s")):
            if variant in d:
                head["description_text"] = fmt % (self.raw(d[variant]) if d[variant] else "")
        for variant, fmt in (("doc key choices", "\\docKeyChoices{%s}"), ("doc key choices*", "\\docKeyChoices*{%s}")):
            if variant in d:
                head["parameter_text"] = fmt % self.raw(d[variant])
        if "doc label" in d:
            head["label"] = self.raw(d["doc label"])
        if "doc keypath" in d:
            head["keypath_raw"] = self.raw(d["doc keypath"]) if d["doc keypath"] else ""
        for key in ("doc new", "doc updated", "doc new and updated"):
            if key in d:
                head[key] = d[key]
        return head

    def doc_entry(self, kind, heads, opts_range, a, b, out, common_kv=None):
        opts = self.kv_dict(opts_range) if opts_range else {}
        if common_kv:
            for key, val in common_kv.items():
                opts.setdefault(key, val)
        headlines = []
        for head in heads:
            if opts_range:
                extra = self._head_from_kv(opts)
                for key, val in extra.items():
                    if key == "name" and "name" in head:
                        continue
                    head.setdefault(key, val)
            headlines.append(self.doc_headline(kind, head, opts))
        body = self.render(self.items(a, b))
        out.append(("b", '<div class="manualentry"><ul class="list" style="list-style-type: none">'
                         + "".join(headlines) + body + "</ul></div>"))

    def doc_headline(self, kind, head, opts):
        name_raw = self.raw(head.get("name")).strip() if head.get("name") else ""
        name_html = esc(re.sub(r"\s+", " ", name_raw))
        label_name = head.get("label", name_raw)
        self.param_mode = True
        if "parameter_text" in head:
            param = self.inline_text(head["parameter_text"])
        else:
            param = self.inline(head.get("parameter")) if head.get("parameter") else ""
        self.param_mode = False
        red = f'<span class="textcolor" style="color: {DEF_COLOR}">'
        if kind == "command":
            label = f"com:{label_name}"
            text = "\\" + name_raw
            headline = f'<kbd>\\{red}{name_html}</span></kbd>{param}'
            self.ctx.known_commands.setdefault(name_raw, label)
        elif kind == "environment":
            label = f"env:{label_name}"
            text = name_raw
            headline = (f'<kbd>\\begin{{{red}{name_html}</span>}}</kbd>{param}<br />'
                        f'<span class="spaces">  </span><span class="angle">&langle;</span><i>environment content</i>'
                        f'<span class="angle">&rangle;</span><br /><kbd>\\end{{{red}{name_html}</span>}}</kbd>')
            self.ctx.known_envs.setdefault(name_raw, label)
        elif kind == "path":
            label = f"path:{label_name}"
            text = name_raw
            headline = f'<kbd>\\path … {red}{name_html}</span></kbd>{param}<kbd> …;</kbd>'
        else:
            path = head.get("keypath", "")
            prefix = f"/{path}/" if path else ""
            label = f"key:{prefix}{label_name}"
            text = f"{prefix}{name_raw}"
            headline = (f'<kbd><span class="keyname">{red}{esc(prefix)}{name_html}</span></span></kbd>{param}')
            if path == "tcb" or (path.startswith("tcb/") and name_raw not in self.ctx.known_keys):
                if self.ctx.known_keys.get(name_raw, "").count("/") != 2 or path == "tcb":
                    self.ctx.known_keys[name_raw] = label
        anchor = pretty_id(label)
        self.ctx.add_label(label, slug=self.slug, anchor=anchor, text=text, kind=kind)
        if kind == "key" and name_raw.startswith("skin=") is False and "skin" == name_raw:
            pass
        desc = ""
        if head.get("description_text"):
            desc = f'<span class="hl-default">({self.inline_text(head["description_text"])})</span>'
        elif head.get("description"):
            desc = f'<span class="hl-default">({self.inline(head["description"])})</span>'
        notes = []
        for key, cls, txt in (("doc new", "docnew", "New"), ("doc updated", "docupdated", "Updated")):
            if head.get(key):
                notes.append(f'<span class="{cls}">{txt}: {self.inline(head[key])}</span>')
        if head.get("doc new and updated"):
            r = head["doc new and updated"]
            parts = re.findall(r"\{([^}]*)\}", self.raw(r))
            if len(parts) == 2:
                notes.append(f'<span class="docnew">New: {esc(parts[0])}</span>')
                notes.append(f'<span class="docupdated">Updated: {esc(parts[1])}</span>')
        notes_html = f'<span class="docnotes">{"".join(notes)}</span>' if notes else ""
        return (f'<div class="entryheadline"><li><p><span class="hl-def">{headline}</span>{desc}{notes_html}'
                f'<a class="anchor-link" href="#{esc(anchor)}" id="{esc(anchor)}">&para;</a></p></li></div>')

    def env_docSkin(self, k, a, b, after, out):
        args, a2 = read_args(self.s, a, "om")
        name = self.raw(args[1]).strip()
        self.ctx.add_label(f"skin:{name}", slug=self.slug, anchor=pretty_id(f"key:/tcb/skin={name}"),
                           text=name, kind="skin")
        head = {"name": None, "keypath": "tcb", "label": f"skin={name}",
                "parameter_text": f"=\\docValue{{{name}}}", "description": None}
        # synthesize the headline
        self.param_mode = True
        param = self.inline_text(head["parameter_text"])
        self.param_mode = False
        label = f"key:/tcb/skin={name}"
        anchor = pretty_id(label)
        self.ctx.add_label(label, slug=self.slug, anchor=anchor, text=f"/tcb/skin={name}", kind="key")
        desc = ""
        opts = self.kv_dict(args[0]) if args[0] else {}
        notes = ""
        if "doc new" in opts:
            notes = f'<span class="docnotes"><span class="docnew">New: {self.inline(opts["doc new"])}</span></span>'
        if "doc updated" in opts:
            notes = f'<span class="docnotes"><span class="docupdated">Updated: {self.inline(opts["doc updated"])}</span></span>'
        headline = (f'<kbd><span class="keyname"><span class="textcolor" style="color: {DEF_COLOR}">/tcb/skin</span></span></kbd>'
                    f'{param}')
        hl = (f'<div class="entryheadline"><li><p><span class="hl-def">{headline}</span>'
              f'<span class="hl-default">(skin)</span>{notes}'
              f'<a class="anchor-link" href="#{esc(anchor)}" id="{esc(anchor)}">&para;</a></p></li></div>')
        body = self.render(self.items(a2, b))
        out.append(("b", '<div class="manualentry"><ul class="list" style="list-style-type: none">'
                         + hl + body + "</ul></div>"))



# generic handlers for the doc key environments defined by \tcbmakedocSubKey
SUBKEY_ENVS = {}
SUBKEYS_ENVS = {}


def install_subkey_envs(sty_text):
    for m in re.finditer(r"\\tcbmakedocSubKey\{(\w+)\}\{([^}]*)\}", sty_text):
        SUBKEY_ENVS[m.group(1)] = m.group(2)
    for m in re.finditer(r"\\tcbmakedocSubKeys\{(\w+)\}\{([^}]*)\}", sty_text):
        SUBKEYS_ENVS[m.group(1)] = m.group(2)
    SUBKEY_ENVS["docKey"] = ""
    SUBKEYS_ENVS["docKeys"] = ""
    for env, path in SUBKEY_ENVS.items():
        def h(self, k, a, b, after, out, path=path):
            self._doc_key(k, a, b, out, path)
        setattr(TcbConverter, "env_" + env, h)
        setattr(TcbConverter, "env_" + env + "_", h)
    for env, path in SUBKEYS_ENVS.items():
        def h(self, k, a, b, after, out, path=path):
            self._doc_keys(k, a, b, out, path)
        setattr(TcbConverter, "env_" + env, h)

    def h_commands(self, k, a, b, after, out):
        self._doc_keys(k, a, b, out, "", kind="command")

    def h_envs(self, k, a, b, after, out):
        self._doc_keys(k, a, b, out, "", kind="environment")
    TcbConverter.env_docCommands = h_commands
    TcbConverter.env_docEnvironments = h_envs



def read_source(stem):
    with open(os.path.join(DOC, f"tcolorbox.doc.{stem}.tex"), encoding="utf-8") as f:
        return f.read()



def preamble_listings():
    with open(os.path.join(DOC, "tcolorbox.doc.s_snippet.sty"), encoding="utf-8") as f:
        text = f.read()
    out = {}
    for m in re.finditer(r"\\begin\{tcbverbatimwrite\}\{\\jobname_preamble_(\w+)\.tex\}\n(.*?)\\end\{tcbverbatimwrite\}",
                         text, re.S):
        out[m.group(1)] = m.group(2)
    return out


def convert_all(ctx):
    return convert_pages(ctx, CHAPTERS, read_source, TcbConverter)


def write_instrumented_tex(ctx, pages):
    shutil.copytree(DOC, TEXDIR, ignore=shutil.ignore_patterns("*.pdf", "external", "solutions"),
                    dirs_exist_ok=True)
    for name in os.listdir(DOC):
        if name.endswith(".pdf") and name != "tcolorbox.pdf":
            shutil.copy(os.path.join(DOC, name), TEXDIR)
    shutil.copy(os.path.join(SHARED, "texhtml", "tikzdev-capture.sty"), TEXDIR)
    shutil.copy(os.path.join(HERE, "tcbhtml.sty"), TEXDIR)
    shutil.copy(os.path.join(HERE, "tcbhtml-compat.sty"), TEXDIR)
    for page in pages:
        s = instrument(read_source(page.stem), page.captures)
        with open(os.path.join(TEXDIR, f"tcolorbox.doc.{page.stem}.tex"), "w", encoding="utf-8") as f:
            f.write(s)

    # main file
    with open(os.path.join(DOC, "tcolorbox.tex"), encoding="utf-8") as f:
        main = f.read()
    main = main.replace("\\tcbEXTERNALIZE\n", "")
    main = "\\RequirePackage{tcbhtml-compat}\n" + main
    main = main.replace("\\usepackage{tcolorbox.doc.s_snippet}",
                        "\\usepackage{tcolorbox.doc.s_snippet}\n\\usepackage{tcbhtml}")
    with open(os.path.join(TEXDIR, "tcolorbox-html.tex"), "w", encoding="utf-8") as f:
        f.write(main)
    os.makedirs(os.path.join(TEXDIR, "external"), exist_ok=True)
    os.makedirs(os.path.join(TEXDIR, "solutions"), exist_ok=True)
    for d in ("external", "solutions"):
        open(os.path.join(TEXDIR, d, "dir.marker"), "w").close()
    n = sum(1 for p in pages for c in p.captures if c[3] != "raw")
    print(f"Wrote instrumented sources to {TEXDIR} ({n} image fragments)")



def home_html(ctx, pages):
    abstract = ("<p><span class=\"verb\">tcolorbox</span> provides an environment for colored and framed text boxes with a "
                "heading line. Optionally, such a box can be split in an upper and a lower part. The package "
                "<span class=\"verb\">tcolorbox</span> can be used for the setting of " + LATEX_LOGO + " examples where one "
                "part of the box displays the source code and the other part shows the output. Another common use "
                "case is the setting of theorems. The package supports saving and reuse of source code and text parts.</p>")
    cover = ""
    if os.path.exists(os.path.join(SITE, IMGDIR_NAME, "cover.png")):
        cover = f'<div class="titlepagepic"><img alt="tcolorbox cover" src="{IMGDIR_NAME}/cover.png" width="420" /></div>'
    sections = []
    for part_id, part_name in PARTS:
        lis = "".join(f'<li><a href="{p.slug}">{p.section_number}&ensp;{toc_title(p)}</a></li>'
                      for p in pages if p.part == part_id)
        if part_id == "appendix":
            lis += '<li><a href="references">References</a></li>'
        sections.append(f'<div class="home-toc-section"><h3><a href="{part_id}">{part_name}</a></h3><ul>{lis}</ul></div>')
    main = f"""
<div class="manual-title-block">
<div class="manual-title">The <span class="texttt">tcolorbox</span> package</div>
<div class="manual-version">Manual for version {ctx.version} ({ctx.date})</div>
<div class="manual-authorship-explanation">Thomas F. Sturm</div>
<div class="manual-html-title">HTML version of the official documentation</div>
<div class="manual-html-explanation">This is an unofficial HTML rendering of the
<a href="https://ctan.org/pkg/tcolorbox">tcolorbox</a> manual, generated from its LaTeX sources.</div>
</div>
{cover}
<div class="abstract"><p class="abstract-title">Abstract</p>{abstract}</div>
<div class="home-toc">{''.join(sections)}</div>
"""
    return main


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "html"
    ctx = Context()
    with open(os.path.join(DOC, "tcolorbox.tex"), encoding="utf-8") as f:
        main_tex = f.read()
    ctx.version = re.search(r"\\def\\version\{([^}]*)\}", main_tex).group(1)
    ctx.date = re.search(r"\\def\\datum\{([^}]*)\}", main_tex).group(1)
    with open(os.path.join(DOC, "tcolorbox.doc.s_main.sty"), encoding="utf-8") as f:
        install_subkey_envs(f.read())
    ctx.preamble_listings = preamble_listings()
    ctx.bib = parse_bib(os.path.join(DOC, "tcolorbox.doc.bib"))
    if mode == "html":
        load_images(ctx, os.path.join(BUILD, "images"))
    # pass 1: collect labels and known names; pass 2: produce final HTML
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
        print(f"Wrote {len(pages)} chapter pages to {SITE}")
    for msg, count in ctx.warnings.most_common(60):
        print(f"  warning ({count}x): {msg}")


if __name__ == "__main__":
    main()
