#!/usr/bin/env python3
"""Finish the wheelchart manual with the shared tikz.dev presentation."""
from functools import partial
from pgf_contrib_site import Manual, build_site, finish_page

MANUAL = Manual(
    package='wheelchart', title='wheelchart Manual', jobname='wheelchart',
    pages={'index.html': 'Drawing charts with wheelchart', 'usage.html': 'Usage',
           'main-macro.html': 'The main macro', 'additional-macros.html': 'Additional macros',
           'keys.html': 'Keys', 'examples.html': 'Additional examples',
           'version-history.html': 'Version history', 'references.html': 'References',
           'key-index.html': 'Index', 'source-code.html': 'The source code'},
    description='Documentation and examples for wheelchart: pie charts, bar charts, infographics and other diagrams with TikZ.',
    pdf_url='https://mirrors.ctan.org/graphics/pgf/contrib/wheelchart/wheelchart.pdf',
    source_url='https://ctan.org/tex-archive/graphics/pgf/contrib/wheelchart',
    author='Matthias Floré',
    notice='''\
wheelchart documentation:
Copyright 2022-2026 Matthias Floré

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, either version 1.3c of this license or (at your
option) any later version.''',
    page_aliases=(('References.html', 'references.html'), ('Index-0.html', 'key-index.html')),
)
PAGES = MANUAL.pages
IMAGES = MANUAL.images
finish_page = partial(finish_page, manual=MANUAL)
main = partial(build_site, MANUAL)

if __name__ == '__main__':
    main()
