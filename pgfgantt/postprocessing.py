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
    pdf_url='https://mirrors.ctan.org/graphics/pgf/contrib/pgfgantt/pgfgantt.pdf',
    source_url='https://github.com/skafdasschaf/latex-pgfgantt',
    pair_adjacent_examples=True,
)
PAGES = MANUAL.pages
IMAGES = MANUAL.images
finish_page = partial(finish_page, manual=MANUAL)
main = partial(build_site, MANUAL)

if __name__ == '__main__':
    main()
