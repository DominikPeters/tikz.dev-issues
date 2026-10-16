"""Compatibility helpers for the lwarp HTML consumed by both manuals."""
import re


_COLORED_TOKEN = re.compile(
    r'(<span\b(?=[^>]*\bclass="textcolor")[^>]*>)(.*?)(</span>)', re.S
)
_INLINE_HTML = re.compile(
    r'</?(?:a|span|br|em|strong|b|i|code|kbd|samp|sub|sup|small|s|del|ins|u|mark|cite|q|var)\b[^<>]*>'
)


def escape_code_angles(html):
    """Keep plain colored SVG/C++ tokens from becoming HTML elements."""
    def escape(match):
        token = match[2]
        # Linked or formatted tokens already contain generated HTML.
        if _INLINE_HTML.search(token):
            return match[0]
        token = token.replace("<", "&lt;").replace(">", "&gt;")
        return match[1] + token + match[3]
    return _COLORED_TOKEN.sub(escape, html)


def normalize_page_layout(soup):
    """Use the wrapper class expected by tikz.dev's layout and stylesheet."""
    if soup.find(class_="bodyandsidetoc") is not None:
        return
    container = soup.select_one("div.pagegrid, div.homepagegrid")
    if container is None:
        raise ValueError("lwarp HTML has no page layout container")
    container["class"] = [
        name for name in container.get("class", [])
        if name not in {"pagegrid", "homepagegrid"}
    ] + ["bodyandsidetoc"]
