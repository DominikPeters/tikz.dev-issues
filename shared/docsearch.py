"""DocSearch v3 assets and header container shared by all manual builds."""
from bs4 import BeautifulSoup


DOCSEARCH_ASSETS = '''<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@docsearch/css@3">
<script defer src="https://cdn.jsdelivr.net/npm/@docsearch/js@3"></script>'''


def add_docsearch(soup):
    """Load the widget before DOMContentLoaded; pgfmanual.js initializes it."""
    soup.head.append(BeautifulSoup(DOCSEARCH_ASSETS, 'html.parser'))
    if soup.select_one('header #search') is None:
        soup.header.append(soup.new_tag('div', id='search'))
