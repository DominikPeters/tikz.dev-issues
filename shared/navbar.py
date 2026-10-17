"""Package menus in the tikz.dev header, shared by the builds of all manuals.

The pgf manual gets an "Other Packages" menu next to its title; the other
manuals get a menu on their title for switching between manuals. Links are
relative, so that a copy of the site below another path (tikz.dev/monorepo/)
links to itself.
"""

# The tikz.dev repository (issues, "About this HTML version")
REPO_URL = "https://github.com/DominikPeters/tikz.dev-issues"
ISSUES_URL = REPO_URL + "/issues"

# package, name in the menu, folder below the site root
PACKAGES = [
    ("pgf", 'PGF/<span class="tikzname">TikZ</span>', ""),
    ("pgfplots", "PGFplots", "pgfplots/"),
    ("tcolorbox", "tcolorbox", "tcolorbox/"),
    ("tikz-cd", "tikz-cd", "tikz-cd/"),
    ("pgf-pie", "pgf-pie", "pgf-pie/"),
    ("tikz-feynman", "TikZ-Feynman", "tikz-feynman/"),
    ("wheelchart", "wheelchart", "wheelchart/"),
    ("pgfgantt", "pgfgantt", "pgfgantt/"),
    ("tkz-euclide", "tkz-euclide", "tkz-euclide/"),
    ("chemfig", "chemfig", "chemfig/"),
]
FOLDERS = {pkg: folder for pkg, _, folder in PACKAGES}

CARET = (
    '<svg class="pkg-menu-caret" viewBox="0 0 10 6" aria-hidden="true">'
    '<path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def home_url(current, pkg):
    """URL of the start page of `pkg`, relative to a page of `current`."""
    if pkg == current:
        return "./"
    return "../" * FOLDERS[current].count("/") + FOLDERS[pkg] or "./"


def _items(current, skip_current):
    items = []
    for pkg, name, _ in PACKAGES:
        if pkg == current and skip_current:
            continue
        mark = ' aria-current="page"' if pkg == current else ""
        items.append(f'<li><a href="{home_url(current, pkg)}"{mark}>{name}</a></li>')
    return f'<ul class="pkg-menu-list">{"".join(items)}</ul>'


def other_packages_menu(current):
    """'Other Packages' button with a menu of the other manuals."""
    return (
        '<span class="pkg-menu">'
        '<button type="button" class="pkg-menu-button" aria-expanded="false">'
        f'Other Packages{CARET}</button>'
        f"{_items(current, skip_current=True)}</span>"
    )


def title_menu(current, title):
    """Manual title (a link to its start page) with a menu of all manuals."""
    return (
        '<span class="pkg-menu">'
        f'<a href="{home_url(current, current)}">{title}</a>'
        '<button type="button" class="pkg-menu-button" aria-expanded="false" '
        f'aria-label="Other manuals">{CARET}</button>'
        f"{_items(current, skip_current=False)}</span>"
    )
