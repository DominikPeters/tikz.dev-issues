#!/usr/bin/env python3
"""Finish the pgfgantt manual with the shared tikz.dev presentation."""
from functools import partial
from pgf_contrib_site import Manual, build_site, finish_page

MANUAL = Manual(
    package='pgfgantt', title='pgfgantt Manual', jobname='pgfgantt-manual',
    pages={'index.html': 'Drawing Gantt charts with pgfgantt',
           'introduction.html': 'Introduction', 'user-guide.html': 'User guide',
           'implementation.html': 'Implementation', 'key-index.html': 'Index'},
    description='Documentation and examples for drawing Gantt charts with pgfgantt and TikZ.',
    pdf_url='https://mirrors.ctan.org/graphics/pgf/contrib/pgfgantt/pgfgantt-doc.pdf',
    source_url='https://github.com/skafdasschaf/latex-pgfgantt',
    author='Wolfgang Esser-Skala',
    notice='''\
pgfgantt documentation:
Copyright (C) 2024 by Wolfgang Esser-Skala

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, either version 1.3c of this license or (at your
option) any later version.''',
    pair_adjacent_examples=True,
)
PAGES = MANUAL.pages
IMAGES = MANUAL.images
finish_page = partial(finish_page, manual=MANUAL)
main = partial(build_site, MANUAL)

if __name__ == '__main__':
    main()
