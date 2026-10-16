#!/usr/bin/env python3
"""Convert the tcolorbox manual to HTML in the style of tikz.dev.

Instead of running the manual through lwarp, this script parses the LaTeX
sources of the manual directly. It understands the macros of the
`documentation` library of tcolorbox (docCommand, docTcbKey, dispExample,
\\refKey, ...) and maps them onto the HTML structure produced by the tikz.dev
pipeline, so that the same style.css and pgfmanual.js apply.

Everything that is genuinely visual (the compiled part of examples, boxes in
running text, pictures, tables, ...) becomes an image. For that, the script
writes an instrumented copy of the manual into build/tex in which each such
fragment is marked with an identifier (see tcbhtml.sty). Compiling that copy
with LuaLaTeX produces one extra PDF page per fragment, which build.sh crops
and converts.

Usage:
    convert.py tex     write the instrumented LaTeX sources
    convert.py html    write the HTML pages (uses images if present)
"""

import datetime
import html
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.normpath(os.path.join(HERE, "..", "doc", "latex", "tcolorbox"))
BUILD = os.path.join(HERE, "build")
TEXDIR = os.path.join(BUILD, "tex")
SITE = os.path.join(BUILD, "site", "tcolorbox")
IMGDIR_NAME = "tcolorbox-images"
BASE_URL = "https://tikz.dev/tcolorbox/"

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

KEY_COLOR = "#008000"
CS_COLOR = "#0000b2"
DEF_COLOR = "#bf0000"

LATEX_LOGO = ('<span class="latexlogofont"><span class="latexlogo">L<span class="latexlogosup">a</span>'
              'T<span class="latexlogosub">e</span>X</span></span>')
TEX_LOGO = '<span class="latexlogofont"><span class="latexlogo">T<span class="latexlogosub">e</span>X</span></span>'

ACCENTS = {
    '"': {"a": "ä", "o": "ö", "u": "ü", "A": "Ä", "O": "Ö", "U": "Ü", "e": "ë", "i": "ï"},
    "'": {"e": "é", "a": "á", "o": "ó", "E": "É", "i": "í", "u": "ú"},
    "`": {"e": "è", "a": "à", "o": "ò", "u": "ù"},
    "^": {"e": "ê", "a": "â", "o": "ô", "i": "î", "u": "û"},
    "~": {"n": "ñ", "a": "ã", "o": "õ"},
    "c": {"c": "ç", "C": "Ç"},
}

SIMPLE_SYMBOLS = {
    "ldots": "…", "dots": "…", "textbackslash": "\\", "textbar": "|", "S": "§",
    "flqq": "«", "frqq": "»", "glqq": "„", "grqq": "“", "copyright": "©",
    "textasciitilde": "~", "textasciicircum": "^", "textless": "&lt;", "textgreater": "&gt;",
    "textbullet": "•", "textendash": "–", "textemdash": "—", "quad": "\u2003",
    "qquad": "\u2003\u2003", "enspace": "\u2002", "ss": "ß", "dag": "†",
    "textregistered": "®", "texttrademark": "™", "LaTeXe": None, "o": "ø", "aa": "å",
    "tcbexclamation": "!", "space": " ", "slash": "/",
}

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

FONT_SWITCHES = {
    "bfseries": "b", "itshape": "i", "slshape": "i", "ttfamily": "kbd", "em": "em",
    "sffamily": None, "rmfamily": None, "scshape": None, "large": None, "Large": None,
    "LARGE": None, "huge": None, "Huge": None, "small": None, "footnotesize": None,
    "scriptsize": None, "tiny": None, "normalsize": None, "color": None,
}

XCOLOR_BASE = {
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "black": (0, 0, 0),
    "white": (255, 255, 255), "yellow": (255, 255, 0), "cyan": (0, 255, 255),
    "magenta": (255, 0, 255), "gray": (128, 128, 128), "orange": (255, 128, 0),
    "violet": (128, 0, 128), "purple": (191, 0, 64), "brown": (191, 128, 64),
    "teal": (0, 128, 128), "olive": (128, 128, 0), "lime": (191, 255, 0),
    "darkgray": (64, 64, 64), "lightgray": (191, 191, 191), "pink": (255, 191, 191),
    "navy": (0, 0, 128), "darkviolet": (148, 0, 211), "darkred": (139, 0, 0),
    "darkgreen": (0, 100, 0),
}


def xcolor_to_css(expr):
    """Approximate an xcolor expression like red!50!black by a CSS color."""
    expr = expr.strip()
    parts = expr.split("!")
    base = XCOLOR_BASE.get(parts[0].lower())
    if base is None:
        return None
    rgb = base
    i = 1
    while i < len(parts):
        try:
            pct = float(parts[i]) / 100
        except ValueError:
            return None
        other = XCOLOR_BASE.get(parts[i + 1].lower(), (255, 255, 255)) if i + 1 < len(parts) else (255, 255, 255)
        rgb = tuple(pct * a + (1 - pct) * b for a, b in zip(rgb, other))
        i += 2
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


def esc(text):
    return html.escape(text, quote=False)


def pretty_id(label):
    """Map a LaTeX label of a documentation entry to a readable HTML id."""
    kind, _, name = label.partition(":")
    if kind == "key":
        return name.lstrip("/").replace(" ", ":")
    if kind == "com":
        return "\\" + name.replace(" ", ":")
    if kind == "env":
        return "env-" + name.replace(" ", ":")
    if kind == "path":
        return "path-" + name.replace(" ", ":")
    return re.sub(r"[^A-Za-z0-9_:./=-]", "-", label)


# --------------------------------------------------------------------------
# Global state shared by all chapters
# --------------------------------------------------------------------------

class Context:
    def __init__(self):
        self.labels = {}  # label -> dict(slug, anchor, text, kind)
        self.known_commands = {}  # name -> label
        self.known_envs = {}
        self.known_keys = {}  # key name (without path) -> label
        self.cited = []
        self.warnings = Counter()
        self.images = {}  # image id -> dict(file, width, height)
        self.preamble_listings = {}
        self.pass_no = 1
        self.bib = {}
        self.cite_numbers = {}

    def warn(self, msg):
        self.warnings[msg] += 1

    def add_label(self, label, **info):
        if label not in self.labels or self.pass_no == 1:
            self.labels.setdefault(label, info)

    def href(self, label, current_slug):
        info = self.labels.get(label)
        if info is None:
            return None
        if info["slug"] == current_slug:
            return "#" + info["anchor"]
        return info["slug"] + "#" + info["anchor"]


# --------------------------------------------------------------------------
# Low level scanning helpers
# --------------------------------------------------------------------------

class ParseError(Exception):
    pass


def skip_comment(s, k):
    """k points at '%'. Return position after the comment, newline, and indentation."""
    nl = s.find("\n", k)
    if nl == -1:
        return len(s)
    k = nl + 1
    while k < len(s) and s[k] in " \t":
        k += 1
    return k


def match_brace(s, k, open_ch="{", close_ch="}"):
    """s[k] == open_ch. Return index of the matching close_ch."""
    depth = 0
    n = len(s)
    i = k
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "%":
            i = s.find("\n", i)
            if i == -1:
                break
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        elif open_ch == "[" and c == "{":
            j = match_brace(s, i)
            i = j + 1
            continue
        i += 1
    raise ParseError(f"unbalanced {open_ch} at {k}: {s[k:k+60]!r}")


def skip_ws(s, k, newlines=True):
    n = len(s)
    while k < n:
        c = s[k]
        if c in " \t" or (newlines and c == "\n"):
            k += 1
        elif c == "%":
            k = skip_comment(s, k)
        else:
            break
    return k


def read_cs(s, k):
    """s[k] == '\\'. Return (name, end)."""
    j = k + 1
    if j >= len(s):
        return "", j
    if s[j].isalpha() or s[j] == "@":
        while j < len(s) and (s[j].isalpha() or s[j] == "@"):
            j += 1
        return s[k + 1:j], j
    return s[j], j + 1


def read_args(s, k, spec, end=None):
    """Read arguments according to spec (s: star, o: optional, m: mandatory).

    Returns (list of values, new position). Optional/mandatory values are
    (start, end) ranges (content only) or None; stars are booleans."""
    args = []
    for t in spec:
        k2 = skip_ws(s, k)
        if t == "*":
            if k2 < len(s) and s[k2] == "*":
                args.append(True)
                k = k2 + 1
            else:
                args.append(False)
        elif t == "o":
            if k2 < len(s) and s[k2] == "[":
                e = match_brace(s, k2, "[", "]")
                args.append((k2 + 1, e))
                k = e + 1
            else:
                args.append(None)
        elif t == "m":
            if k2 >= len(s):
                args.append(None)
                continue
            if s[k2] == "{":
                e = match_brace(s, k2)
                args.append((k2 + 1, e))
                k = e + 1
            elif s[k2] == "\\":
                _, e = read_cs(s, k2)
                args.append((k2, e))
                k = e
            else:
                args.append((k2, k2 + 1))
                k = k2 + 1
    return args, k


def find_env_end(s, k, name, verbatim=False):
    """k is just after \\begin{name}. Return (body_end, after_end)."""
    endtag = "\\end{" + name + "}"
    if verbatim:
        e = s.find(endtag, k)
        if e == -1:
            raise ParseError("missing " + endtag)
        return e, e + len(endtag)
    begintag = "\\begin{" + name + "}"
    depth = 1
    i = k
    while True:
        nb = s.find(begintag, i)
        ne = s.find(endtag, i)
        if ne == -1:
            raise ParseError("missing " + endtag)
        # ignore occurrences in comments
        if nb != -1 and nb < ne:
            if _in_comment(s, nb):
                i = nb + len(begintag)
                continue
            depth += 1
            i = nb + len(begintag)
        else:
            if _in_comment(s, ne):
                i = ne + len(endtag)
                continue
            depth -= 1
            if depth == 0:
                return ne, ne + len(endtag)
            i = ne + len(endtag)


def _in_comment(s, k):
    ls = s.rfind("\n", 0, k) + 1
    line = s[ls:k]
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "%":
            return True
        i += 1
    return False


def split_kv(s, a, b):
    """Split a key-value list s[a:b] at top-level commas.

    Returns a list of (key, value_range or None)."""
    out = []
    items = []
    depth = 0
    start = a
    i = a
    while i < b:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "%":
            i = s.find("\n", i)
            if i == -1 or i > b:
                i = b
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            items.append((start, i))
            start = i + 1
        i += 1
    items.append((start, b))
    for x, y in items:
        txt = s[x:y]
        if not txt.strip() or not re.sub(r"%[^\n]*", "", txt).strip():
            continue
        eq = _top_level_eq(s, x, y)
        if eq is None:
            out.append((_clean_key(s[x:y]), None))
        else:
            vx, vy = eq + 1, y
            # strip whitespace and one level of braces
            while vx < vy and s[vx] in " \t\n":
                vx += 1
            while vy > vx and s[vy - 1] in " \t\n":
                vy -= 1
            if vx < vy and s[vx] == "{" and match_brace(s, vx) == vy - 1:
                vx, vy = vx + 1, vy - 1
            out.append((_clean_key(s[x:eq]), (vx, vy)))
    return out


def _clean_key(k):
    k = re.sub(r"%[^\n]*", "", k)
    return " ".join(k.split())


def _top_level_eq(s, a, b):
    depth = 0
    i = a
    while i < b:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "=" and depth == 0:
            return i
        i += 1
    return None


def split_items(s, a, b, cmd="\\item"):
    """Split s[a:b] at top-level occurrences of cmd. Returns list of (start, end)."""
    positions = []
    depth = 0
    i = a
    while i < b:
        c = s[i]
        if c == "%":
            i = skip_comment(s, i)
            continue
        if c == "\\":
            if s.startswith("\\begin{", i):
                name_end = s.index("}", i)
                name = s[i + 7:name_end]
                _, after = find_env_end(s, name_end + 1, name, name in VERBATIM_ENVS)
                i = after
                continue
            if depth == 0 and s.startswith(cmd, i) and not (i + len(cmd) < b and s[i + len(cmd)].isalpha()):
                positions.append(i)
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    ranges = []
    for idx, p in enumerate(positions):
        ranges.append((p + len(cmd), positions[idx + 1] if idx + 1 < len(positions) else b))
    return ranges


# --------------------------------------------------------------------------
# Code highlighting
# --------------------------------------------------------------------------

KEY_CANDIDATE = re.compile(r"(?<=[\[,{])([ \t]*\n?[ \t]*)([A-Za-z][A-Za-z0-9 \-]*?[A-Za-z0-9])(?=[ \t]*\n?[ \t]*[=,\]}/])")


def dedent_code(code):
    lines = code.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(line.rstrip() for line in lines)


def highlight(code, ctx, slug):
    """Render LaTeX code like the tikz.dev code examples (with links)."""
    code = code.expandtabs(2)
    marks = {}  # start -> (end, html_open, html_close)
    for m in KEY_CANDIDATE.finditer(code):
        key = m.group(2)
        label = ctx.known_keys.get(key)
        if label is None:
            continue
        s0 = m.start(2)
        marks[s0] = (m.end(2), "key", label)
    out = []
    i = 0
    n = len(code)
    after_begin = False

    def link(text, label, color):
        href = ctx.href(label, slug) if label else None
        inner = esc(text)
        if href:
            inner = f'<a href="{esc(href)}">{inner}</a>'
        return f'<span class="textcolor" style="color: {color}">{inner}</span>'

    while i < n:
        c = code[i]
        if i in marks:
            e, kind, label = marks[i]
            out.append(link(code[i:e], label, KEY_COLOR))
            i = e
            continue
        if c == "%":
            e = code.find("\n", i)
            if e == -1:
                e = n
            out.append(f'<span class="example-code-comment">{esc(code[i:e])}</span>')
            i = e
            continue
        if c == "\\":
            name, e = read_cs(code, i)
            if name.isalpha() or "@" in name:
                if name in ("begin", "end"):
                    out.append(f'<span class="textcolor" style="color: #000000">\\{name}</span>')
                    # environment name
                    if e < n and code[e] == "{":
                        ce = code.find("}", e)
                        if ce != -1:
                            env = code[e + 1:ce]
                            out.append("{" + link(env, ctx.known_envs.get(env), CS_COLOR) + "}")
                            i = ce + 1
                            continue
                else:
                    out.append(link("\\" + name, ctx.known_commands.get(name), CS_COLOR))
            else:
                out.append(esc(code[i:e]))
            i = e
            continue
        if c == "\n":
            out.append("<br />\n")
            i += 1
            j = i
            while j < n and code[j] == " ":
                j += 1
            if j > i:
                out.append('<span class="spaces">' + " " * (j - i) + "</span>")
            i = j
            continue
        if c == " " and i + 1 < n and code[i + 1] == " ":
            j = i
            while j < n and code[j] == " ":
                j += 1
            out.append('<span class="spaces">' + " " * (j - i) + "</span>")
            i = j
            continue
        out.append(esc(c))
        i += 1
    return "".join(out)


def code_block(code, ctx, slug, title=None):
    body = highlight(dedent_code(code), ctx, slug)
    t = f'<div class="example-code-title">{title}</div>' if title else ""
    return (f'<div class="example-code">{t}<button class="clipboardButton" type="button">copy</button>'
            f"<code>{body}<br /></code></div>")


# --------------------------------------------------------------------------
# The converter
# --------------------------------------------------------------------------

class Converter:
    """Converts one LaTeX source text to HTML."""

    def __init__(self, ctx, text, slug, file_stem=None, page=None):
        self.ctx = ctx
        self.s = text
        self.slug = slug
        self.stem = file_stem
        self.page = page  # Page object collecting sections, footnotes, ...
        self.captures = []  # (start, end, image id, kind)
        self.counter = 0
        self.param_mode = False
        self.aliases = {}
        self.user_macros = {}  # name -> argument spec
        self.last_temp = ""  # code last written by dispListing/dispExample/tcbwritetemp

    # -- images --------------------------------------------------------------

    def new_image(self, start, end, kind):
        if self.stem is None:
            self.ctx.warn("image outside chapter")
            return None
        self.counter += 1
        image_id = f"{self.stem}-{self.counter}"
        self.captures.append((start, end, image_id, kind))
        return image_id

    def img_html(self, image_id, inline=False, alt="Compiled output"):
        info = self.ctx.images.get(image_id)
        if info is None:
            if self.ctx.images:  # images were built, but this one is empty
                return ""
            return f'<span class="missing-image">[{image_id}]</span>'
        cls = "lateximage" + (" inlineimage" if inline else "")
        return (f'<img alt="{esc(alt)}" class="{cls}" loading="lazy" src="{IMGDIR_NAME}/{info["file"]}" '
                f'width="{info["width"]:.3f}" height="{info["height"]:.3f}" />')

    def at_line_start(self, k):
        line_start = self.s.rfind("\n", 0, k) + 1
        return self.s[line_start:k].strip() in ("", "{")

    # -- core loop -----------------------------------------------------------

    def items(self, a, b):
        """Convert s[a:b]. Returns list of ('i', html) | ('b', html) | ('p',)."""
        s = self.s
        out = []
        buf = []

        def flush():
            if buf:
                text = "".join(buf)
                buf.clear()
                if self.param_mode and text.strip():
                    out.append(("i", "<kbd>" + text + "</kbd>"))
                else:
                    out.append(("i", text))

        k = a
        while k < b:
            c = s[k]
            if c == "%":
                k = skip_comment(s, k)
                continue
            if c == "\\":
                flush()
                k = self.command(k, b, out)
                continue
            if c == "{":
                flush()
                e = match_brace(s, k)
                out.extend(self.group(k + 1, e))
                k = e + 1
                continue
            if c == "}":
                k += 1
                continue
            if c == "$":
                flush()
                k = self.math(k, b, out)
                continue
            if c == "\n" or c in " \t":
                j = k
                newlines = 0
                while j < b and (s[j] in " \t\n" or s[j] == "%"):
                    if s[j] == "\n":
                        newlines += 1
                    if s[j] == "%":
                        j = skip_comment(s, j)
                        newlines = 0
                        continue
                    j += 1
                if newlines >= 2:
                    flush()
                    out.append(("p",))
                else:
                    buf.append(" ")
                k = j
                continue
            if c == "~":
                buf.append("\u00a0")
                k += 1
                continue
            if c == "|":
                e = s.find("|", k + 1)
                if e == -1 or e > b:
                    buf.append("|")
                    k += 1
                    continue
                flush()
                out.append(("i", f'<span class="verb">{esc(s[k + 1:e])}</span>'))
                k = e + 1
                continue
            if c == "-":
                if s.startswith("---", k):
                    buf.append("—")
                    k += 3
                elif s.startswith("--", k):
                    buf.append("–")
                    k += 2
                else:
                    buf.append("-")
                    k += 1
                continue
            if c == "`":
                if s.startswith("``", k):
                    buf.append("“")
                    k += 2
                else:
                    buf.append("‘")
                    k += 1
                continue
            if c == "'":
                if s.startswith("''", k):
                    buf.append("”")
                    k += 2
                else:
                    buf.append("’")
                    k += 1
                continue
            if c == "&":
                buf.append("&amp;")
                k += 1
                continue
            buf.append(esc(c))
            k += 1
        flush()
        return out

    def inline(self, r):
        if r is None:
            return ""
        parts = []
        for it in self.items(*r):
            if it[0] == "p":
                parts.append(" ")
            else:
                parts.append(it[1])
        return "".join(parts).strip()

    def raw(self, r):
        if r is None:
            return ""
        return self.s[r[0]:r[1]]

    def plain(self, r):
        """Plain text of an argument (tags stripped)."""
        return html.unescape(re.sub(r"<[^>]+>", "", self.inline(r)))

    def group(self, a, b):
        """A brace group; handle a leading font switch like {\\bfseries ...}."""
        s = self.s
        k = skip_ws(s, a)
        if k < b and s[k] == "\\":
            name, e = read_cs(s, k)
            if name in FONT_SWITCHES:
                tag = FONT_SWITCHES[name]
                if name == "color":
                    args, e = read_args(s, e, "m")
                inner = self.items(e, b)
                if tag and inner:
                    html_inner = "".join(x[1] for x in inner if x[0] != "p")
                    return [("i", f"<{tag}>{html_inner.strip()}</{tag}>")]
                return inner
        return self.items(a, b)

    def math(self, k, b, out):
        s = self.s
        display = s.startswith("$$", k)
        d = 2 if display else 1
        e = s.find("$" * d, k + d)
        if e == -1:
            out.append(("i", "$"))
            return k + 1
        content = s[k + d:e]
        if "tcb" in content or "\\boxed" in content:
            image_id = self.new_image(k, e + d, "inline")
            out.append(("i", self.img_html(image_id, inline=True)))
        else:
            self.page.uses_math = True if self.page else False
            if display:
                out.append(("b", f"<p>\\[{esc(content)}\\]</p>"))
            else:
                out.append(("i", f"\\({esc(content)}\\)"))
        return e + d

    # -- commands ------------------------------------------------------------

    def command(self, k, b, out):
        s = self.s
        name, e = read_cs(s, k)
        # single-character commands
        if not (name.isalpha() or "@" in name):
            if name == "\\":
                args, e2 = read_args(s, e, "*o")
                out.append(("i", "<br />"))
                return e2
            if name in "%&$#_{}":
                out.append(("i", esc(name)))
                return e
            if name in (" ", "\n", "\t"):
                out.append(("i", " "))
                return e
            if name == ",":
                out.append(("i", "\u2009"))
                return e
            if name in ACCENTS:
                args, e2 = read_args(s, e, "m")
                ch = self.raw(args[0]).strip("{}")
                out.append(("i", ACCENTS[name].get(ch, ch)))
                return e2
            if name in "@/-!;:":
                return e
            if name == "[":
                end = s.find("\\]", e)
                if self.page:
                    self.page.uses_math = True
                out.append(("b", f"<p>\\[{esc(s[e:end])}\\]</p>"))
                return end + 2
            if name == "(":
                end = s.find("\\)", e)
                if self.page:
                    self.page.uses_math = True
                out.append(("i", f"\\({esc(s[e:end])}\\)"))
                return end + 2
            out.append(("i", esc(name)))
            return e

        if name == "begin":
            return self.environment(k, e, b, out)

        handler = getattr(self, "cmd_" + name.replace("@", "_at_"), None)
        if handler is not None:
            return handler(k, e, out)
        if name in ACCENTS:
            args, e2 = read_args(s, e, "m")
            ch = self.raw(args[0]).strip("{}")
            out.append(("i", ACCENTS[name].get(ch, ch)))
            return e2
        if name in SIMPLE_SYMBOLS:
            val = SIMPLE_SYMBOLS[name]
            if name == "LaTeXe":
                val = LATEX_LOGO + "2<sub>ε</sub>"
            out.append(("i", val))
            # swallow a following empty group or control space
            if s.startswith("{}", e):
                e += 2
            return e
        if name in IGNORED:
            args, e2 = read_args(s, e, IGNORED[name])
            return e2
        if name in FONT_SWITCHES:
            return e
        if name in self.user_macros:
            args, e2 = read_args(s, e, self.user_macros[name])
            if self.at_line_start(k):
                image_id = self.new_image(k, e2, "block")
                out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
            else:
                image_id = self.new_image(k, e2, "inline")
                out.append(("i", self.img_html(image_id, inline=True)))
            return e2
        if name == "tcbusetemp" and DEFINITION_RE.search(self.last_temp):
            # the code defines things which must stay visible afterwards, so it
            # cannot run inside a capture group; it gets no image
            return e
        if name in INLINE_IMAGE_COMMANDS:
            args, e2 = read_args(s, e, INLINE_IMAGE_SPECS.get(name, "om"))
            if name == "tcboxverb":
                # verbatim argument: braces delimit it
                pass
            if self.at_line_start(k):
                image_id = self.new_image(k, e2, "block")
                out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
            else:
                image_id = self.new_image(k, e2, "inline")
                out.append(("i", self.img_html(image_id, inline=True)))
            return e2
        self.ctx.warn(f"unknown command \\{name}")
        return e

    # simple formatting
    def _wrap(self, e, out, open_tag, close_tag, spec="m"):
        args, e2 = read_args(self.s, e, spec)
        out.append(("i", open_tag + self.inline(args[-1]) + close_tag))
        return e2

    def cmd_textbf(self, k, e, out):
        return self._wrap(e, out, "<b>", "</b>")

    def cmd_textit(self, k, e, out):
        return self._wrap(e, out, "<i>", "</i>")

    cmd_textsl = cmd_textit

    def cmd_emph(self, k, e, out):
        return self._wrap(e, out, "<em>", "</em>")

    def cmd_textsf(self, k, e, out):
        return self._wrap(e, out, "", "")

    cmd_textrm = cmd_textsf
    cmd_textup = cmd_textsf
    cmd_textnormal = cmd_textsf
    cmd_textmd = cmd_textsf
    cmd_hbox = cmd_textsf

    def cmd_textsc(self, k, e, out):
        return self._wrap(e, out, '<span style="font-variant: small-caps">', "</span>")

    def cmd_texttt(self, k, e, out):
        if self.param_mode:
            return self._wrap(e, out, "<kbd>", "</kbd>")
        return self._wrap(e, out, '<span class="texttt">', "</span>")

    def cmd_textcolor(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        color = xcolor_to_css(self.raw(args[0]))
        inner = self.inline(args[1])
        if color:
            out.append(("i", f'<span class="textcolor" style="color: {color}">{inner}</span>'))
        else:
            out.append(("i", inner))
        return e2

    def cmd_tikzname(self, k, e, out):
        out.append(("i", '<span class="tikzname">TikZ</span>'))
        if self.s.startswith("{}", e):
            e += 2
        return e

    def cmd_LaTeX(self, k, e, out):
        out.append(("i", LATEX_LOGO))
        if self.s.startswith("{}", e):
            e += 2
        return e

    def cmd_TeX(self, k, e, out):
        out.append(("i", TEX_LOGO))
        if self.s.startswith("{}", e):
            e += 2
        return e

    def cmd_version(self, k, e, out):
        out.append(("i", self.ctx.version))
        return e

    def cmd_datum(self, k, e, out):
        out.append(("i", self.ctx.date))
        return e

    def cmd_enquote(self, k, e, out):
        return self._wrap(e, out, "“", "”")

    def cmd_url(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        u = self.raw(args[0])
        out.append(("i", f'<a href="{esc(u)}">{esc(u)}</a>'))
        return e2

    def cmd_href(self, k, e, out):
        args, e2 = read_args(self.s, e, "mm")
        u = self.raw(args[0])
        out.append(("i", f'<a href="{esc(u)}">{self.inline(args[1])}</a>'))
        return e2

    def cmd_footnote(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        if self.page is None:
            return e2
        self.page.footnotes.append(self.render(self.items(*args[0])))
        n = len(self.page.footnotes)
        out.append(("i", f'<sup class="footnotemark"><a href="#footnote-{n}" id="footnotemark-{n}">{n}</a></sup>'))
        return e2

    def cmd_item(self, k, e, out):
        # only reached for stray items
        args, e2 = read_args(self.s, e, "o")
        return e2

    def cmd_mylib(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", f'<span class="mylib">{self.inline(args[0])}</span>'))
        return e2

    def cmd_meta(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        saved = self.param_mode
        self.param_mode = False
        inner = self.inline(args[0])
        self.param_mode = saved
        out.append(("i", f'<span class="angle">&langle;</span><i>{inner}</i><span class="angle">&rangle;</span>'))
        return e2

    def _delim_meta(self, e, out, left, right):
        args, e2 = read_args(self.s, e, "m")
        saved = self.param_mode
        self.param_mode = False
        inner = self.inline(args[0])
        self.param_mode = saved
        out.append(("i", f'<kbd>{left}</kbd><span class="angle">&langle;</span><i>{inner}</i>'
                         f'<span class="angle">&rangle;</span><kbd>{right}</kbd>'))
        return e2

    def cmd_marg(self, k, e, out):
        return self._delim_meta(e, out, "{", "}")

    def cmd_oarg(self, k, e, out):
        return self._delim_meta(e, out, "[", "]")

    def cmd_pbarg(self, k, e, out):
        return self._delim_meta(e, out, "(", ")")

    def cmd_sarg(self, k, e, out):
        out.append(("i", "<kbd>*</kbd>"))
        return e

    def cmd_brackets(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", "<kbd>{</kbd>" + self.inline(args[0]) + "<kbd>}</kbd>"))
        return e2

    def cmd_cs(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        name = self.raw(args[0])
        label = self.ctx.known_commands.get(name)
        txt = esc("\\" + name)
        href = self.ctx.href(label, self.slug) if label else None
        tag = "kbd" if self.param_mode else 'span class="texttt"'
        endtag = tag.split()[0]
        if href:
            out.append(("i", f'<a href="{esc(href)}"><{tag}>{txt}</{endtag}></a>'))
        else:
            out.append(("i", f"<{tag}>{txt}</{endtag}>"))
        return e2

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

    def inline_text(self, txt):
        sub = Converter(self.ctx, txt, self.slug, None, self.page)
        sub.param_mode = self.param_mode
        return sub.inline((0, len(txt)))

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

    def _label_link(self, label, text=None):
        info = self.ctx.labels.get(label)
        href = self.ctx.href(label, self.slug)
        if info is None:
            if self.ctx.pass_no == 2:
                self.ctx.warn(f"unresolved label {label}")
            return "??"
        if text is None:
            text = info["text"]
        return f'<a href="{esc(href)}">{text}</a>'

    def cmd_ref(self, k, e, out):
        args, e2 = read_args(self.s, e, "*m")
        out.append(("i", self._label_link(self.raw(args[1]).strip())))
        return e2

    def cmd_pageref(self, k, e, out):
        return self.cmd_ref(k, e, out)

    def _zref(self, k, e, out, with_type=True):
        args, e2 = read_args(self.s, e, "*om")
        links = []
        for label in self.raw(args[2]).split(","):
            label = label.strip()
            info = self.ctx.labels.get(label)
            if info is None:
                links.append(self._label_link(label))
                continue
            text = info["text"]
            if with_type and info["kind"] in ("section", "subsection", "subsubsection"):
                text = "Section&nbsp;" + text
            links.append(self._label_link(label, text))
        out.append(("i", ", ".join(links)))
        return e2

    def cmd_zvref(self, k, e, out):
        return self._zref(k, e, out)

    def cmd_zcref(self, k, e, out):
        return self._zref(k, e, out)

    def cmd_zcpageref(self, k, e, out):
        return self._zref(k, e, out)

    def cmd_cite(self, k, e, out):
        args, e2 = read_args(self.s, e, "om")
        keys = [x.strip() for x in self.raw(args[1]).split(",")]
        nums = []
        for key in keys:
            if key not in self.ctx.cited:
                self.ctx.cited.append(key)
            n = self.ctx.cite_numbers.get(key, "?")
            nums.append(f'<a href="references#{esc(key)}">{n}</a>')
        extra = (", " + self.inline(args[0])) if args[0] else ""
        out.append(("i", "[" + ", ".join(nums) + extra + "]"))
        return e2

    def cmd_citetitle(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        key = self.raw(args[0]).strip()
        entry = self.ctx.bib.get(key, {})
        out.append(("i", f"<i>{esc(tex_to_text(entry.get('title', key)))}</i>"))
        return e2

    def cmd_inputpreamblelisting(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        code = self.ctx.preamble_listings.get(self.raw(args[0]).strip(), "")
        out.append(("b", '<figure class="example">'
                         + code_block(code, self.ctx, self.slug, title="Definition in the preamble:")
                         + "</figure>"))
        return e2

    def cmd_label(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        label = self.raw(args[0]).strip()
        if self.page is not None:
            anchor = re.sub(r"[^A-Za-z0-9_:.-]", "-", label)
            self.ctx.add_label(label, slug=self.slug, anchor=anchor, text=self.page.current_number, kind="label")
            out.append(("i", f'<a id="{esc(anchor)}"></a>'))
        return e2

    def cmd_let(self, k, e, out):
        m = re.match(r"\s*\\([A-Za-z@]+)\s*=?\s*\\([A-Za-z@]+)", self.s[e:])
        if not m:
            return e
        new, old = m.group(1), m.group(2)
        self.aliases[new] = old
        if new.startswith("end") and old.startswith("end"):
            self.aliases[new[3:]] = old[3:]
        return e + m.end()

    def cmd_def(self, k, e, out):
        m = re.match(r"\\([A-Za-z@]+)((?:#\d)*)\s*\{", self.s[e:])
        if not m:
            return e
        brace = e + m.end() - 1
        self.user_macros[m.group(1)] = "m" * (len(m.group(2)) // 2)
        return match_brace(self.s, brace) + 1

    cmd_gdef = cmd_def
    cmd_edef = cmd_def

    def cmd_newcommand(self, k, e, out):
        args, e2 = read_args(self.s, e, "*moom")
        name = self.raw(args[1]).strip().lstrip("\\")
        n = int(self.raw(args[2])) if args[2] else 0
        self.user_macros[name] = ("o" if args[3] else "m") + "m" * (n - 1) if n else ""
        return e2

    cmd_renewcommand = cmd_newcommand
    cmd_providecommand = cmd_newcommand
    cmd_newrobustcmd = cmd_newcommand

    def _xparse_define(self, e, extra_args):
        args, e2 = read_args(self.s, e, "mm" + "m" * extra_args)
        name = self.raw(args[0]).strip().lstrip("\\")
        spec = ""
        for tok in re.findall(r"[a-zA-Z](?:\{[^}]*\})?", self.raw(args[1])):
            spec += {"s": "*", "o": "o", "O": "o", "m": "m", "v": "m", "+": ""}.get(tok[0], "m")
        self.user_macros[name] = spec
        return e2

    def cmd_NewDocumentCommand(self, k, e, out):
        return self._xparse_define(e, 1)

    cmd_DeclareDocumentCommand = cmd_NewDocumentCommand
    cmd_RenewDocumentCommand = cmd_NewDocumentCommand

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

    def cmd_verb(self, k, e, out):
        s = self.s
        star = s[e] == "*"
        if star:
            e += 1
        delim = s[e]
        end = s.find(delim, e + 1)
        out.append(("i", f'<span class="verb">{esc(s[e + 1:end])}</span>'))
        return end + 1

    def cmd_textbraceleft(self, k, e, out):
        out.append(("i", "{"))
        return e

    def cmd_textbraceright(self, k, e, out):
        out.append(("i", "}"))
        return e

    def cmd_detokenize(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.append(("i", esc(self.raw(args[0]))))
        return e2

    def cmd_bgroup(self, k, e, out):
        return e

    cmd_egroup = cmd_bgroup
    cmd_tcbinterruptdraftmode = cmd_bgroup
    cmd_tcbcontinuedraftmode = cmd_bgroup

    def cmd_kern(self, k, e, out):
        m = re.match(r"\s*-?[\d.]+\s*[a-z]{2}", self.s[e:])
        return e + (m.end() if m else 0)

    def cmd_lipsum(self, k, e, out):
        args, e2 = read_args(self.s, e, "o")
        out.append(("i", "Lorem ipsum dolor sit amet, consectetuer adipiscing elit. …"))
        return e2

    def cmd_input(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        return e2

    def cmd_section(self, k, e, out):
        return self.heading(k, e, out, 1)

    def cmd_subsection(self, k, e, out):
        return self.heading(k, e, out, 2)

    def cmd_subsubsection(self, k, e, out):
        return self.heading(k, e, out, 3)

    def heading(self, k, e, out, level):
        args, e2 = read_args(self.s, e, "*om")
        title = self.inline(args[2])
        # look for a label right after the heading
        k2 = skip_ws(self.s, e2)
        labels = []
        while True:
            # skip \tcbdocmarginnote{...} etc. between heading and label
            m = re.match(r"\\label\{([^}]*)\}", self.s[k2:])
            if not m:
                break
            labels.append(m.group(1))
            k2 = skip_ws(self.s, k2 + m.end())
        page = self.page
        number = page.next_number(level)
        page.current_number = number
        anchor = "sec-" + number
        kind = ["section", "subsection", "subsubsection"][level - 1]
        for label in labels:
            self.ctx.add_label(label, slug=self.slug, anchor=anchor, text=number, kind=kind)
        tag = {1: "h4", 2: "h5", 3: "h6"}[level]
        label_anchors = "".join(f'<a id="{esc(lb)}"></a>' for lb in labels)
        out.append(("b", f'<{tag}>{label_anchors}<span><span class="sectionnumber" id="{anchor}">{number}</span> '
                         f'{title}</span><a class="anchor-link" href="#{anchor}">&para;</a></{tag}>'))
        if level == 1:
            page.title = re.sub(r"<[^>]+>", "", title).strip()
            page.title_html = title
        elif level == 2:
            page.toc.append(("tocsubsection", anchor, title))
        else:
            page.toc.append(("tocsubsubsection", anchor, title))
        return k2

    # -- environments --------------------------------------------------------

    def environment(self, k, e, b, out):
        s = self.s
        args, e2 = read_args(s, e, "m")
        name = self.raw(args[0])
        body_start = e2
        verbatim = name in VERBATIM_ENVS
        try:
            body_end, after = find_env_end(s, body_start, name, verbatim)
        except ParseError as err:
            self.ctx.warn(str(err))
            return body_start
        handler = getattr(self, "env_" + re.sub(r"\W", "_", self.aliases.get(name, name)), None)
        if handler is not None:
            handler(k, body_start, body_end, after, out)
            return after
        if name in SILENT_VERBATIM_ENVS:
            if name == "tcbwritetemp":
                self.last_temp = s[body_start:body_end]
            return after
        if name in TRANSPARENT_ENVS:
            if name in ("multicols", "minipage"):
                _, body_start = read_args(s, body_start, "om" if name == "multicols" else "oooom")
            out.extend(self.items(body_start, body_end))
            return after
        # everything else is rendered as an image
        image_id = self.new_image(k, after, "block")
        out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
        return after

    def env_itemize(self, k, a, b, after, out, tag="ul"):
        lis = []
        for x, y in split_items(self.s, a, b):
            args, x2 = read_args(self.s, x, "o")
            label = ""
            if args[0] and tag == "dl":
                label = self.inline(args[0])
            body = self.render(self.items(x2, y))
            if tag == "dl":
                lis.append(f"<dt>{label}</dt><dd>{body}</dd>")
            elif args[0]:
                lis.append(f'<li class="customlabel"><span class="listmarker">{self.inline(args[0])}</span> {body}</li>')
            else:
                lis.append(f"<li>{body}</li>")
        out.append(("b", f"<{tag}>" + "".join(lis) + f"</{tag}>"))

    def env_enumerate(self, k, a, b, after, out):
        self.env_itemize(k, a, b, after, out, tag="ol")

    def env_description(self, k, a, b, after, out):
        self.env_itemize(k, a, b, after, out, tag="dl")

    def env_center(self, k, a, b, after, out):
        out.append(("b", f'<div class="center">{self.render(self.items(a, b))}</div>'))

    def env_quote(self, k, a, b, after, out):
        out.append(("b", f"<blockquote>{self.render(self.items(a, b))}</blockquote>"))

    env_absquote = env_quote
    env_quotation = env_quote

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

    def kv_dict(self, r):
        d = {}
        for key, val in split_kv(self.s, *r):
            d[key] = val
        return d

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

    def render(self, items):
        """Group inline items into paragraphs."""
        html_parts = []
        para = []

        def end_para():
            text = "".join(para).strip()
            para.clear()
            if text:
                html_parts.append(f"<p>{text}</p>")

        for it in items:
            if it[0] == "i":
                para.append(it[1])
            elif it[0] == "p":
                end_para()
            else:
                end_para()
                html_parts.append(it[1])
        end_para()
        return "\n".join(html_parts)


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
        setattr(Converter, "env_" + env, h)
        setattr(Converter, "env_" + env + "_", h)
    for env, path in SUBKEYS_ENVS.items():
        def h(self, k, a, b, after, out, path=path):
            self._doc_keys(k, a, b, out, path)
        setattr(Converter, "env_" + env, h)

    def h_commands(self, k, a, b, after, out):
        self._doc_keys(k, a, b, out, "", kind="command")

    def h_envs(self, k, a, b, after, out):
        self._doc_keys(k, a, b, out, "", kind="environment")
    Converter.env_docCommands = h_commands
    Converter.env_docEnvironments = h_envs


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

class Page:
    def __init__(self, stem, slug, part, section_number):
        self.stem = stem
        self.slug = slug
        self.part = part
        self.section_number = section_number  # "1" or "A"
        self.counters = [0, 0]
        self.title = slug
        self.title_html = slug
        self.toc = []
        self.footnotes = []
        self.uses_math = False
        self.body = ""
        self.first_heading_done = False
        self.current_number = section_number

    def next_number(self, level):
        if level == 1:
            self.counters = [0, 0]
            return self.section_number
        if level == 2:
            self.counters[0] += 1
            self.counters[1] = 0
            return f"{self.section_number}.{self.counters[0]}"
        self.counters[1] += 1
        return f"{self.section_number}.{self.counters[0]}.{self.counters[1]}"


def read_source(stem):
    with open(os.path.join(DOC, f"tcolorbox.doc.{stem}.tex"), encoding="utf-8") as f:
        return f.read()


def parse_bib(path):
    with open(path, encoding="latin-1") as f:
        text = f.read()
    entries = {}
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        start = m.end()
        depth = 1
        i = m.end() - 1
        # find end of entry by brace matching from the opening brace
        i = text.index("{", m.start())
        end = match_brace(text, i)
        body = text[start:end]
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*", body):
            j = fm.end()
            if j < len(body) and body[j] == "{":
                e = match_brace(body, j)
                val = body[j + 1:e]
            else:
                e = body.find(",", j)
                e = len(body) if e == -1 else e
                val = body[j:e]
            fields.setdefault(fm.group(1).lower(), " ".join(val.replace("{", "").replace("}", "").split()))
        fields["type"] = m.group(1).lower()
        entries[m.group(2)] = fields
    return entries


def tex_to_text(s):
    s = s.replace("\\LaTeX", "LaTeX").replace("\\TeX", "TeX")
    s = re.sub(r"\\['\"`^~]\{?(\w)\}?", lambda m: ACCENTS.get(m.group(0)[1], {}).get(m.group(1), m.group(1)), s)
    s = s.replace("~", "\u00a0").replace("--", "–").replace("\\&", "&")
    s = s.replace("\\ ", " ")
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    return s


def preamble_listings():
    with open(os.path.join(DOC, "tcolorbox.doc.s_snippet.sty"), encoding="utf-8") as f:
        text = f.read()
    out = {}
    for m in re.finditer(r"\\begin\{tcbverbatimwrite\}\{\\jobname_preamble_(\w+)\.tex\}\n(.*?)\\end\{tcbverbatimwrite\}",
                         text, re.S):
        out[m.group(1)] = m.group(2)
    return out


def convert_all(ctx):
    pages = []
    section_no = 0
    appendix_no = 0
    for stem, slug, part in CHAPTERS:
        if part == "appendix":
            appendix_no += 1
            number = chr(ord("A") + appendix_no - 1)
        else:
            section_no += 1
            number = str(section_no)
        page = Page(stem, slug, part, number)
        conv = Converter(ctx, read_source(stem), slug, stem, page)
        items = conv.items(0, len(conv.s))
        page.body = conv.render(items)
        page.captures = conv.captures
        pages.append(page)
    return pages


def write_instrumented_tex(ctx, pages):
    shutil.copytree(DOC, TEXDIR, ignore=shutil.ignore_patterns("*.pdf", "external", "solutions"),
                    dirs_exist_ok=True)
    for name in os.listdir(DOC):
        if name.endswith(".pdf") and name != "tcolorbox.pdf":
            shutil.copy(os.path.join(DOC, name), TEXDIR)
    shutil.copy(os.path.join(HERE, "tcbhtml.sty"), TEXDIR)
    shutil.copy(os.path.join(HERE, "tcbhtml-compat.sty"), TEXDIR)
    for page in pages:
        s = read_source(page.stem)
        inserts = []  # (position, text)
        for start, end, image_id, kind in page.captures:
            if kind == "raw":  # image_id holds literal text to insert
                inserts.append((start, image_id))
            elif kind == "example":
                inserts.append((start, f"\\HTMLnext{{{image_id}}}%\n"))
            elif kind == "block":
                inserts.append((start, f"\\begin{{HTMLcapture}}{{{image_id}}}%\n"))
                inserts.append((end, f"%\n\\end{{HTMLcapture}}"))
            else:
                inserts.append((start, f"\\HTMLinlinebegin{{{image_id}}}"))
                inserts.append((end, "\\HTMLinlineend{}"))
        # stable order: later positions first; at equal positions keep end-markers after begin-markers
        for pos, text in sorted(inserts, key=lambda x: x[0], reverse=True):
            s = s[:pos] + text + s[pos:]
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


# --------------------------------------------------------------------------
# HTML assembly
# --------------------------------------------------------------------------

def page_shell(ctx, pages, page, title, main_html, local_toc, is_home=False):
    today = datetime.date.today().isoformat()
    version = today.replace("-", "")
    # chapter toc
    toc = ['<p></p>']
    cls = ' class="current"' if is_home else ""
    toc.append(f'<p{cls}><a class="linkintro" href="./">Home</a></p>')
    current_part = page.part if page else None
    for part_id, part_name in PARTS:
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
                toc.append(f'<p{c}><a class="tocsection" href="{p.slug}">{toc_title(p)}</a></p>')
    local = "".join(f'<p><a class="{c}" href="#{a}">{t}</a></p>' for c, a, t in local_toc)
    mathjax = ""
    if page is not None and page.uses_math:
        mathjax = '<script async id="MathJax-script" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>'
    part_h2 = ""
    if page is not None and page.part is not None and page.slug not in dict(PARTS):
        part_h2 = f'<h2 class="inserted">{dict(PARTS)[page.part]}</h2>'
    canonical = BASE_URL + ("" if is_home else page.slug)
    return f"""<!DOCTYPE html>
<html lang="en-US">
<!--The tcolorbox package documentation:
Copyright (c) 2006-2026 by Prof. Dr. Dr. Thomas F. Sturm

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, either version 1.3 of this license or (at your
option) any later version.

tikz.dev:
Copyright 2021-2026 Dominik Peters
This file may be distributed and/or modified under the LaTeX Project Public License.-->
<head>
<meta charset="utf-8" />
<meta content="width=device-width, initial-scale=1.0" name="viewport" />
<title>{esc(title)}</title>
<link href="style.css?v={version}" rel="stylesheet" type="text/css" />
<link href="tcolorbox.css?v={version}" rel="stylesheet" type="text/css" />
{mathjax}
<script src="pgfmanual.js?v={version}"></script>
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
<strong><a href="https://tikz.dev" style="font-weight: normal">tikz.dev / </a><a href="./">tcolorbox Manual</a></strong>
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
<div class="sidetoctitle"><p><span class="sidetocthetitle">The tcolorbox package</span></p><p>Contents</p></div>
<div class="sidetoccontents">
{chr(10).join(toc)}
</div>
</nav>
</div>
<main class="bodycontainer">
<section class="textbody">
<h1>The tcolorbox package</h1>
{part_h2}
{main_html}
</section>
</main>
<footer>
<div class="footer-left">
<a href="https://www.latex-project.org/lppl/">License</a> &middot; <a href="https://ctan.org/pkg/tcolorbox">CTAN</a> &middot;
<a href="https://mirrors.ctan.org/macros/latex/contrib/tcolorbox/tcolorbox.pdf">Official PDF version</a> &middot;
<a href="https://github.com/T-F-S/tcolorbox">tcolorbox on GitHub</a> &middot;
<a href="https://github.com/DominikPeters/tikz.dev-issues/issues">Feedback and issues</a>
</div>
<div class="footer-right"><em>HTML version last updated: {today}</em></div>
</footer>
</div>
</body>
</html>
"""


def toc_title(page):
    """Section title for tables of contents (library badges become plain text)."""
    return re.sub(r'<span class="mylib">(.*?)</span>', r"\1", page.title_html)


def footnotes_html(page):
    if not page.footnotes:
        return ""
    items = "".join(f'<p id="footnote-{i}"><sup><a href="#footnotemark-{i}">{i}</a></sup> {fn[3:-4] if fn.startswith("<p>") and fn.count("<p>") == 1 else fn}</p>'
                    for i, fn in enumerate(page.footnotes, 1))
    return f'<div class="footnotes">{items}</div>'


def fix_page_refs(html_text):
    # "page~\pageref{x}" makes no sense in HTML; the label resolves to a section number
    return re.sub(r"([Pp])age(\u00a0|\s)(<a [^>]*>)", lambda m: ("S" if m.group(1) == "P" else "s") + "ection&nbsp;" + m.group(3), html_text)


def write_site(ctx, pages):
    os.makedirs(SITE, exist_ok=True)
    for name in ("style.css", "pgfmanual.js", "tcolorbox.css"):
        shutil.copy(os.path.join(HERE, "assets", name), SITE)
    img_src = os.path.join(BUILD, "images")
    if os.path.isdir(img_src):
        dst = os.path.join(SITE, IMGDIR_NAME)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(img_src, dst, ignore=shutil.ignore_patterns("*.pdf", "dims.json"))
    for page in pages:
        main = page.body + footnotes_html(page)
        main = fix_page_refs(main)
        out = page_shell(ctx, pages, page, f"{page.title} - tcolorbox Manual", main, page.toc)
        with open(os.path.join(SITE, page.slug + ".html"), "w", encoding="utf-8") as f:
            f.write(out)
    # part pages
    for part_id, part_name in PARTS:
        part_page = Page(None, part_id, part_id, "")
        part_page.title_html = part_name
        items = "".join(f'<li><a href="{p.slug}">{p.section_number}&ensp;{toc_title(p)}</a></li>'
                        for p in pages if p.part == part_id)
        main = f'<h3>{part_name}</h3><div class="mobile-toc part-toc"><ul>{items}</ul></div>'
        with open(os.path.join(SITE, part_id + ".html"), "w", encoding="utf-8") as f:
            f.write(page_shell(ctx, pages, part_page, f"{part_name} - tcolorbox Manual", main, []))
    # references
    write_references(ctx, pages)
    # home page
    write_home(ctx, pages)


def write_references(ctx, pages):
    entries = []
    for key in ctx.cited_sorted:
        e = ctx.bib.get(key, {})
        n = ctx.cite_numbers[key]
        author = tex_to_text(e.get("author", e.get("editor", ""))).replace(" and ", ", ")
        title = tex_to_text(e.get("title", key))
        rest = []
        for field in ("subtitle", "edition", "publisher", "location", "organization", "date", "year"):
            if e.get(field):
                val = tex_to_text(e[field])
                if field == "edition" and val.isdigit():
                    val = f"{val}. edition"
                rest.append(val)
        url = e.get("url", "")
        url_html = f'<br /><a href="{esc(url)}">{esc(url)}</a>' if url else ""
        entries.append(f'<p class="bibitem" id="{esc(key)}"><span class="biblabel">[{n}]</span> '
                       f'{esc(author)}. <i>{esc(title)}</i>. {esc(". ".join(rest))}{"." if rest else ""}{url_html}</p>')
    ref_page = Page(None, "references", "appendix", "")
    ref_page.title_html = "References"
    main = '<h4><span><span class="sectionnumber" id="sec-refs"></span> References</span></h4>' + "".join(entries)
    with open(os.path.join(SITE, "references.html"), "w", encoding="utf-8") as f:
        f.write(page_shell(ctx, pages, ref_page, "References - tcolorbox Manual", main, []))


def write_home(ctx, pages):
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
    home_page = Page(None, "index", None, "")
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(page_shell(ctx, pages, home_page, "tcolorbox Manual - Complete Online Documentation", main, [], is_home=True))


def load_images(ctx):
    dims = os.path.join(BUILD, "images", "dims.json")
    if os.path.exists(dims):
        with open(dims) as f:
            ctx.images = json.load(f)


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
        load_images(ctx)
    # pass 1: collect labels and known names; pass 2: produce final HTML
    ctx.pass_no = 1
    convert_all(ctx)

    def sort_key(key):
        e = ctx.bib.get(key, {})
        return (tex_to_text(e.get("author", e.get("editor", "zzz"))).split(",")[0].split()[-1:],
                e.get("year", e.get("date", "")), e.get("title", ""))
    ctx.cited_sorted = sorted(ctx.cited, key=sort_key)
    ctx.cite_numbers = {k: i + 1 for i, k in enumerate(ctx.cited_sorted)}
    ctx.pass_no = 2
    ctx.warnings.clear()
    pages = convert_all(ctx)
    if mode == "tex":
        write_instrumented_tex(ctx, pages)
    else:
        write_site(ctx, pages)
        print(f"Wrote {len(pages)} chapter pages to {SITE}")
    for msg, count in ctx.warnings.most_common(60):
        print(f"  warning ({count}x): {msg}")


if __name__ == "__main__":
    main()
