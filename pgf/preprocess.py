#!/usr/bin/env python3
"""Mechanical edits to the upstream pgf manual, run by scripts/prepare.py
before the patches in patches/ are applied.

Every chapter file pgfmanual-en-<name>.tex gets the page name <name> as the
optional argument of its \\section, which lwarp uses as the file name of the
HTML page (tikz.dev/<name>). New upstream chapters thus get a page without
needing a patch.
"""
import os
import re
import sys

# page names that differ from the file name (kept for stable URLs)
PAGE_NAMES = {
    "introduction": "index",
    "library-angles": "library-angle",
    "library-calendar": "library-calender",
    "library-matrices": "library-matrix",
}

SECTION = re.compile(r"^\\section(\[[^\]\n]*\])?(?=\s*\{)", re.M)


def main(tree):
    docdir = os.path.join(tree, "doc", "generic", "pgf")
    for name in sorted(os.listdir(docdir)):
        m = re.fullmatch(r"pgfmanual-en-(.+)\.tex", name)
        if not m:
            continue
        path = os.path.join(docdir, name)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        page = PAGE_NAMES.get(m.group(1), m.group(1))
        text, n = SECTION.subn(lambda _: f"\\section[{page}]", text, count=1)
        if n:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)


if __name__ == "__main__":
    main(sys.argv[1])
