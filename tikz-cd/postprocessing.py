#!/usr/bin/env python3
"""Finish this manual with the shared tikz.dev presentation."""
from functools import partial

from pgf_contrib_site import Manual, build_site, finish_page


MANUAL = Manual(
    package='tikz-cd',
    title='tikz-cd Manual',
    jobname='tikz-cd-doc',
    pages={
        'index.html': 'Commutative diagrams with TikZ',
        'getting-started.html': 'Getting started',
        'diagram-options.html': 'Controlling the appearance of diagrams',
        'advanced-usage.html': 'Advanced usage',
        'additional-goodies.html': 'Additional goodies',
    },
    description='Documentation and examples for tikz-cd, commutative diagrams with TikZ.',
    pdf_url='https://mirrors.ctan.org/graphics/pgf/contrib/tikz-cd/tikz-cd-doc.pdf',
    source_url='https://github.com/astoff/tikz-cd',
    author='Augusto Stoffel',
    notice='''\
tikz-cd documentation:
Copyright 2011, 2012, 2014, 2018, 2021 Augusto Stoffel

This work may be distributed and/or modified under the conditions of the
LaTeX Project Public License, either version 1.3 of this license or (at your
option) any later version.''',
    cover_title='Commutative diagrams',
    ignored_html=(),
)
PAGES = MANUAL.pages
IMAGES = MANUAL.images
finish_page = partial(finish_page, manual=MANUAL)
main = partial(build_site, MANUAL)


if __name__ == '__main__':
    main()
