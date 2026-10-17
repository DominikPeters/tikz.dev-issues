#!/usr/bin/env python3
"""Finish this manual with the shared tikz.dev presentation."""
from functools import partial

from pgf_contrib_site import Manual, build_site, finish_page


MANUAL = Manual(
    package='tikz-feynman',
    title='TikZ-Feynman Manual',
    jobname='tikz-feynman',
    pages={
        'index.html': 'Feynman diagrams with TikZ',
        'introduction.html': 'Introduction',
        'tutorial.html': 'Tutorial',
        'documentation.html': 'Documentation',
        'examples.html': 'Examples',
        'key-index.html': 'Index',
        'references.html': 'References',
    },
    description='Documentation and examples for TikZ-Feynman, Feynman diagrams with TikZ.',
    pdf_url='https://mirrors.ctan.org/graphics/pgf/contrib/tikz-feynman/tikz-feynman.pdf',
    source_url='https://github.com/JP-Ellis/tikz-feynman',
    cover_title='Feynman diagrams',
    ignored_html=(),
)
PAGES = MANUAL.pages
IMAGES = MANUAL.images
finish_page = partial(finish_page, manual=MANUAL)
main = partial(build_site, MANUAL)


if __name__ == '__main__':
    main()
