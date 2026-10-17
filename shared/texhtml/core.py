"""Shared core of the tikz.dev LaTeX-to-HTML converters (tcolorbox, ...).

Some manuals are not converted with lwarp but by parsing their LaTeX sources
directly: each manual is built from a small set of its own documentation
macros, which a converter maps onto the HTML structure of the tikz.dev pages
(manualentry, entryheadline, example, ...). Everything visual (the output of
examples, pictures, boxes in running text, ...) becomes an image: the
converter writes an instrumented copy of the sources in which each such
fragment is marked (see capture.sty), LuaLaTeX ships every marked fragment as
an extra PDF page, and extract_images.py crops and converts those pages.

This module has the generic parts: scanning helpers, the converter for
ordinary LaTeX (text, math, lists, sections, references, footnotes, user
macros), code highlighting, pages and the two-pass driver. A manual subclasses
Converter, adds handlers cmd_<name>/env_<name> for its own macros, and extends
the class-level sets of verbatim, transparent and ignored environments and
commands.
"""

import html
import json
import os
import re
from collections import Counter

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
    "usetikzlibrary": "m", "makeatletter": "",
    "makeatother": "", "par": "", "relax": "", "enlargethispage": "*m", "nopagebreak": "o",
    "pagebreak": "o", "linebreak": "o", "nolinebreak": "o", "allowbreak": "",
    "phantomsection": "", "strut": "", "centering": "", "raggedright": "", "raggedleft": "",
    "addtocontents": "mm", "addcontentsline": "mmm", "setlength": "mm", "addtolength": "mm",
    "pgfkeys": "m", "pgfkeysalso": "m", "tikzset": "m",
    "newcounter": "mo", "setcounter": "mm",
    "stepcounter": "m", "newlength": "m", "definecolor": "mmm", "colorlet": "mm",
    "lstdefinestyle": "mm", "lstset": "m",
    "printbibliography": "o", "printindex": "", "appendix": "",
    "mbox": "", "ignorespaces": "", "unskip": "", "kill": "", "nobreak": "",
    "bookmarksetup": "m", "hypersetup": "m", "AddToHook": "mom", "zcsetup": "m",
    "zcRefTypeSetup": "mm", "pgfplotsset": "m", "@starttoc": "m",
    "lstMakeShortInline": "m", "thispagestyle": "m",
    "pagestyle": "m", "selectlanguage": "m", "BeginAccSupp": "m", "EndAccSupp": "m",
    "nocite": "m", "displaystyle": "", "normalfont": "", "upshape": "", "mdseries": "",
}
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


VERB_RE = re.compile(r"\\[Vv]erb\*?([^A-Za-z*\s])")


def match_brace(s, k, open_ch="{", close_ch="}"):
    """s[k] == open_ch. Return index of the matching close_ch."""
    depth = 0
    n = len(s)
    i = k
    while i < n:
        c = s[i]
        if c == "\\":
            m = VERB_RE.match(s, i)
            if m and not s.endswith("\\string", 0, i):  # \verb|...| may contain unbalanced braces
                end = s.find(m.group(1), m.end())
                if end != -1:
                    i = end + 1
                    continue
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


def split_items(s, a, b, cmd="\\item", verbatim_envs=()):
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
                _, after = find_env_end(s, name_end + 1, name, name in verbatim_envs)
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
    """Converts one LaTeX source text to HTML.

    Subclasses extend the class-level sets below and add handlers
    cmd_<name>(k, e, out) and env_<name>(k, body_start, body_end, after, out).
    """

    # Environments whose body is verbatim (never parsed as LaTeX).
    verbatim_envs = {"verbatim", "lstlisting", "minted"}
    # Verbatim environments that only write files (no output in the document).
    silent_verbatim_envs = set()
    # Environments whose content is converted to HTML (everything else that is
    # unknown becomes an image).
    transparent_envs = {"multicols", "minipage", "flushleft", "flushright", "document",
                        "small", "footnotesize"}
    # Commands that become an image, with argument specs (to find their extent).
    inline_image_commands = {"includegraphics", "tikz", "fbox", "colorbox", "fcolorbox"}
    inline_image_specs = {"includegraphics": "*om", "tikz": "o", "fbox": "m", "colorbox": "mm",
                          "fcolorbox": "mmm"}
    ignored = IGNORED
    # characters delimiting verbatim text, like |\\foo| with \\MakeShortVerb
    short_verb_chars = "|"
    # Folder of the images on the site (relative to the pages).
    img_dir = "images"

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
        self.in_table_cell = False

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
        return (f'<img alt="{esc(alt)}" class="{cls}" loading="lazy" src="{self.img_dir}/{info["file"]}" '
                f'width="{info["width"]:.3f}" height="{info["height"]:.3f}" />')

    def at_line_start(self, k):
        line_start = self.s.rfind("\n", 0, k) + 1
        return self.s[line_start:k].strip() in ("", "{")

    def block_image_at(self, k):
        """Whether a fragment at s[k] is captured as a block (a paragraph of its
        own) rather than inline; never in table cells (no paragraphs there)."""
        return not self.in_table_cell and self.at_line_start(k)

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
            if c in self.short_verb_chars:
                e = s.find(c, k + 1)
                if e == -1 or e > b:
                    buf.append(c)
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
        if self.math_needs_image(content):
            image_id = self.new_image(k, e + d, "inline")
            out.append(("i", self.img_html(image_id, inline=True)))
        else:
            self.page.uses_math = True if self.page else False
            if display:
                out.append(("b", f"<p>\\[{esc(content)}\\]</p>"))
            else:
                out.append(("i", f"\\({esc(content)}\\)"))
        return e + d


    def math_needs_image(self, content):
        """Whether inline math must be rendered by LaTeX instead of MathJax."""
        return False

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
        if name in self.ignored:
            args, e2 = read_args(s, e, self.ignored[name])
            return e2
        if name in FONT_SWITCHES:
            return e
        if name in self.user_macros:
            args, e2 = read_args(s, e, self.user_macros[name])
            if self.block_image_at(k):
                image_id = self.new_image(k, e2, "block")
                out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
            else:
                image_id = self.new_image(k, e2, "inline")
                out.append(("i", self.img_html(image_id, inline=True)))
            return e2
        if name in self.inline_image_commands:
            return self.inline_image(k, e, name, out)
        self.ctx.warn(f"unknown command \\{name}")
        return e

    def inline_image(self, k, e, name, out):
        """A command that becomes an image: a block image if it starts a line."""
        args, e2 = read_args(self.s, e, self.inline_image_specs.get(name, "om"))
        if self.block_image_at(k):
            image_id = self.new_image(k, e2, "block")
            out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
        else:
            image_id = self.new_image(k, e2, "inline")
            out.append(("i", self.img_html(image_id, inline=True)))
        return e2

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


    def inline_text(self, txt):
        sub = type(self)(self.ctx, txt, self.slug, None, self.page)
        sub.param_mode = self.param_mode
        return sub.inline((0, len(txt)))

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
        m = re.match(r"\\([A-Za-z@]+|[^A-Za-z@])((?:#\d)*)\s*\{", self.s[e:])
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
    cmd_begingroup = cmd_bgroup
    cmd_endgroup = cmd_bgroup
    cmd_sloppy = cmd_bgroup

    def cmd_endinput(self, k, e, out):
        # the rest of the file is not read
        return len(self.s)

    cmd_leavevmode = cmd_bgroup
    cmd_protect = cmd_bgroup

    def cmd_string(self, k, e, out):
        """\\string\\cs prints \\cs."""
        s = self.s
        if e < len(s) and s[e] == "\\":
            _, e2 = read_cs(s, e)
            out.append(("i", esc(s[e:e2])))
            return e2
        out.append(("i", esc(s[e:e + 1])))
        return e + 1

    def cmd_char(self, k, e, out):
        m = re.match(r"`\\?(.)|(\d+)", self.s[e:])
        if not m:
            return e
        out.append(("i", esc(m.group(1) if m.group(1) else chr(int(m.group(2))))))
        return e + m.end()

    def cmd_catcode(self, k, e, out):
        m = re.match(r"`\\?.\s*=?\s*\d+\s?", self.s[e:])
        return e + (m.end() if m else 0)

    def cmd_csname(self, k, e, out):
        end = self.s.find("\\endcsname", e)
        return end + len("\\endcsname") if end != -1 else e

    def cmd_hskip(self, k, e, out):
        m = re.match(r"\s*-?[\d.]+\s*[a-z]{2}(\s*(plus|minus)\s*-?[\d.]+\s*[a-z]+)*", self.s[e:])
        return e + (m.end() if m else 0)

    cmd_vskip = cmd_hskip

    def cmd_spaceskip(self, k, e, out):
        """Assignments to dimension registers: skip the value."""
        m = re.match(r"\s*=?\s*(-?[\d.]+\s*[a-z]{2}(\s*(plus|minus)\s*-?[\d.]+\s*[a-z]+)*|\\[A-Za-z@]+)",
                     self.s[e:])
        return e + (m.end() if m else 0)

    cmd_xspaceskip = cmd_spaceskip

    def cmd_vbox(self, k, e, out):
        args, e2 = read_args(self.s, e, "m")
        out.extend(self.group(*args[0]))
        return e2

    cmd_vtop = cmd_vbox

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
        if level == 1 and page.sections == 1:
            page.title = re.sub(r"<[^>]+>", "", title).strip()
            page.title_html = title
        elif level == 1:
            page.toc.append(("tocsection", anchor, title))
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
        verbatim = name in self.verbatim_envs
        try:
            body_end, after = find_env_end(s, body_start, name, verbatim)
        except ParseError as err:
            self.ctx.warn(str(err))
            return body_start
        handler = getattr(self, "env_" + re.sub(r"\W", "_", self.aliases.get(name, name)), None)
        if handler is not None:
            handler(k, body_start, body_end, after, out)
            return after
        if name in self.silent_verbatim_envs:
            return after
        if name in self.transparent_envs:
            if name in ("multicols", "minipage"):
                _, body_start = read_args(s, body_start, "om" if name == "multicols" else "oooom")
            out.extend(self.items(body_start, body_end))
            return after
        # everything else is rendered as an image
        if self.in_table_cell:
            image_id = self.new_image(k, after, "inline")
            out.append(("i", self.img_html(image_id, inline=True)))
            return after
        image_id = self.new_image(k, after, "block")
        out.append(("b", f'<div class="figure">{self.img_html(image_id)}</div>'))
        return after

    def env_itemize(self, k, a, b, after, out, tag="ul"):
        lis = []
        for x, y in split_items(self.s, a, b, verbatim_envs=self.verbatim_envs):
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

    def kv_dict(self, r):
        d = {}
        for key, val in split_kv(self.s, *r):
            d[key] = val
        return d

    # -- tables (opt-in: a subclass sets env_tabular = Converter.env_html_table) --

    TABLE_RULES = re.compile(r"\\(?:toprule|midrule|bottomrule|hline|endhead|endfirsthead|endfoot|endlastfoot)\b"
                             r"(?:\[[^\]]*\])?|\\(?:cmidrule|cline)(?:\([^)]*\))?\{[^}]*\}")
    # macros that stand for a whole table row (see table_row_macro), or for the
    # first cells of a row (table_row_macros_partial)
    table_row_macros = ()
    table_row_macros_partial = ()
    # a first row containing one of these words is a header row
    table_header_words = ("arguments", "options", "option", "argument", "macro", "macros", "default",
                          "definition", "example", "explanation", "styles", "style", "name", "key",
                          "keys", "value", "description", "meaning")
    table_class = "html-table"

    def env_html_table(self, k, a, b, after, out):
        """A tabular (or longtable, tabularx) as an HTML table."""
        name = self.s[self.s.rfind("{", 0, a) + 1:a - 1]
        spec = {"tabularx": "mom", "tabular*": "mom"}.get(name, "om")
        args, a2 = read_args(self.s, a, spec)
        rows = []
        for r0, r1 in self._split_top(a2, b, "\\\\"):
            text = self.s[r0:r1]
            if not self.TABLE_RULES.sub("", re.sub(r"%[^\n]*", "", text)).strip():
                continue
            rows.extend(self._row_cells(r0, r1))
        if not rows:
            return
        html_rows = []
        for i, cells in enumerate(rows):
            tag = "th" if i == 0 and self._looks_like_header(cells) else "td"
            html_rows.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        out.append(("b", f'<div class="table-scroll"><table class="{self.table_class}">'
                         + "".join(html_rows) + "</table></div>"))

    def table_row_macro(self, name, k):
        """For a macro in table_row_macros at s[k:], return (list of cell HTML, end)."""
        raise NotImplementedError

    def _looks_like_header(self, cells):
        plain = [re.sub(r"<[^>]+>", "", c).strip().lower() for c in cells]
        return any(p in self.table_header_words for p in plain)

    def _row_cells(self, r0, r1):
        """Rows in s[r0:r1] (a row macro is a row of its own)."""
        s = self.s
        rows = []
        i = plain_start = r0
        pattern = re.compile(r"\\(" + "|".join(map(re.escape, self.table_row_macros)) + r")(?![A-Za-z])") \
            if self.table_row_macros else None
        while pattern:
            m = pattern.search(s, i, r1)
            if not m:
                break
            before = self.TABLE_RULES.sub("", re.sub(r"%[^\n]*", "", s[plain_start:m.start()]))
            if before.strip():
                rows.append(self._cells(plain_start, m.start()))
            cells, e = self.table_row_macro(m.group(1), m.start())
            if self.table_row_macros_partial and m.group(1) in self.table_row_macros_partial:
                # the rest of the row follows the macro: & more cells
                rest_end = r1
                nxt = pattern.search(s, e, r1)
                if nxt:
                    rest_end = nxt.start()
                more = self._cells(e, rest_end)
                if more and not re.sub(r"<[^>]+>", "", more[0]).strip():
                    more = more[1:]
                cells = cells + more
                e = rest_end
            rows.append(cells)
            i = plain_start = e
        rest = self.TABLE_RULES.sub("", re.sub(r"%[^\n]*", "", s[plain_start:r1]))
        if rest.strip():
            rows.append(self._cells(plain_start, r1))
        return rows

    def _cells(self, r0, r1):
        cells = []
        for c0, c1 in self._split_top(r0, r1, "&"):
            # rules (\\hline, ...) at the start of the cell; converted in place, so
            # that images in cells are captured
            m = re.compile(r"(\s|" + self.TABLE_RULES.pattern + r")*").match(self.s, c0, c1)
            saved, self.in_table_cell = self.in_table_cell, True
            cells.append(self.inline((m.end(), c1)))
            self.in_table_cell = saved
        return cells

    def _split_top(self, a, b, sep):
        """Split s[a:b] at top-level occurrences of sep (outside braces and environments);
        for row separators (\\\\), \\cr counts too."""
        s = self.s
        parts = []
        depth = 0
        start = a
        i = a
        while i < b:
            c = s[i]
            if c == "%":
                nl = s.find("\n", i)
                i = b if nl == -1 or nl > b else nl
                continue
            if depth == 0 and (s.startswith(sep, i) or
                               (sep == "\\\\" and s.startswith("\\cr", i) and not s[i + 3:i + 4].isalpha())):
                parts.append((start, i))
                i += 3 if s.startswith("\\cr", i) else len(sep)
                if sep == "\\\\":
                    args, i = read_args(s, i, "o")
                start = i
                continue
            if c == "\\":
                if s.startswith("\\begin{", i):
                    name_end = s.index("}", i)
                    name = s[i + 7:name_end]
                    _, i = find_env_end(s, name_end + 1, name, name in self.verbatim_envs)
                    continue
                i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        parts.append((start, b))
        return parts

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
        self.sections = 0  # number of top-level headings (a page may have several)
        self.top_number = section_number

    def next_number(self, level):
        if level == 1:
            self.counters = [0, 0]
            self.sections += 1
            if self.sections == 1 or not self.section_number.isdigit():
                self.top_number = self.section_number
            else:
                # further sections in the same source file continue the numbering
                self.top_number = str(int(self.section_number) + self.sections - 1)
            return self.top_number
        if level == 2:
            self.counters[0] += 1
            self.counters[1] = 0
            return f"{self.top_number}.{self.counters[0]}"
        self.counters[1] += 1
        return f"{self.top_number}.{self.counters[0]}.{self.counters[1]}"


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


def footnotes_html(page):
    if not page.footnotes:
        return ""
    items = "".join(f'<p id="footnote-{i}"><sup><a href="#footnotemark-{i}">{i}</a></sup> {fn[3:-4] if fn.startswith("<p>") and fn.count("<p>") == 1 else fn}</p>'
                    for i, fn in enumerate(page.footnotes, 1))
    return f'<div class="footnotes">{items}</div>'


def fix_page_refs(html_text):
    # "page~\pageref{x}" makes no sense in HTML; the label resolves to a section number
    return re.sub(r"([Pp])age(\u00a0|\s)(<a [^>]*>)", lambda m: ("S" if m.group(1) == "P" else "s") + "ection&nbsp;" + m.group(3), html_text)


def convert_pages(ctx, chapters, read_source, converter, appendix_parts=("appendix",)):
    """Convert all chapters (stem, slug, part); returns their Page objects.

    Chapters in appendix parts are numbered A, B, ..., the others 1, 2, ..."""
    pages = []
    section_no = 0
    appendix_no = 0
    for stem, slug, part in chapters:
        if part in appendix_parts:
            appendix_no += 1
            number = chr(ord("A") + appendix_no - 1)
        else:
            section_no += 1
            number = str(section_no)
        page = Page(stem, slug, part, number)
        conv = converter(ctx, read_source(stem), slug, stem, page)
        items = conv.items(0, len(conv.s))
        page.body = conv.render(items)
        page.captures = conv.captures
        pages.append(page)
        if part not in appendix_parts:
            section_no += max(page.sections - 1, 0)
    return pages


def instrument(source, captures):
    """Insert the capture markers of capture.sty into a chapter source.

    captures are (start, end, image id, kind) as recorded by Converter.new_image;
    kind "raw" inserts the text given as image id at start."""
    inserts = []  # (position, text)
    for start, end, image_id, kind in captures:
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
        source = source[:pos] + text + source[pos:]
    return source


def load_images(ctx, images_dir):
    """Image sizes written by extract_images.py, if the images were built."""
    dims = os.path.join(images_dir, "dims.json")
    if os.path.exists(dims):
        with open(dims) as f:
            ctx.images = json.load(f)
