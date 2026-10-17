#!/usr/bin/env python3
"""Finish this manual with the shared tikz.dev presentation."""
from functools import partial

from pgf_contrib_site import Manual, build_site, finish_page


MANUAL = Manual(
    package='pgf-pie',
    title='pgf-pie Manual',
    jobname='pgf-pie-manual',
    pages={
        'index.html': 'Drawing pie charts with pgf-pie',
        'usage.html': 'Usage',
        'variant-charts.html': 'Variant charts',
        'examples.html': 'Examples',
        'acknowledgements.html': 'Acknowledgements',
    },
    description='Documentation and examples for pgf-pie, pie charts with TikZ.',
    pdf_url='https://mirrors.ctan.org/graphics/pgf/contrib/pgf-pie/pgf-pie-manual.pdf',
    source_url='https://github.com/pgf-tikz/pgf-pie',
    author='Yuan Xu',
    notice='''\
pgf-pie documentation:
Copyright 2011-2020 Yuan Xu

pgf-pie is licensed under the terms of the LaTeX Project Public License (LPPL)
1.3c, or alternatively under the terms of the GNU General Public License (GPL)
version 2.''',
    cover_title='',
    ignored_html=('description.html',),
)
PAGES = MANUAL.pages
IMAGES = MANUAL.images
finish_page = partial(finish_page, manual=MANUAL)
main = partial(build_site, MANUAL)


if __name__ == '__main__':
    main()
