"""Author–year labels for citations: [Tantau 2025] instead of [5].

Used by the converted manuals (from the .bib fields, texhtml/site.py) and the
lwarp manuals (from their printed reference lists, pgf_contrib_site.py).
"""
import re

YEAR = re.compile(r"\b(1[6-9]\d\d|20\d\d)\b")


def last_name(name):
    """Last name of "First Last", "F. M. Last" or "Last, First"."""
    name = " ".join(name.replace("{", "").replace("}", "").split())
    if "," in name:
        return name.split(",")[0].strip()
    words = name.split()
    return words[-1] if words else ""


def author_year(authors, year=""):
    """Label from a list of author names and a year: "Tantau 2025",
    "Collins and Vermaseren 2016", "Binosi et al. 2009"."""
    names = [last_name(a) for a in authors if a.strip()]
    others = any(n.lower() in ("others", "al.") for n in names)
    names = [n for n in names if n and n.lower() not in ("others", "al.")]
    if len(names) >= 3 or (names and others):
        who = f"{names[0]} et al."
    elif len(names) == 2:
        who = f"{names[0]} and {names[1]}"
    else:
        who = names[0] if names else ""
    return " ".join(part for part in (who, year) if part)


def split_names(text, bibtex=False):
    """Author names from a BibTeX field ("A and B") or printed text ("A, B and C")."""
    if bibtex:
        return [n for n in re.split(r"\s+and\s+", text) if n.strip()]
    return [n for n in re.split(r",\s*|\s+and\s+|\s*&\s*", text) if n.strip()]


def entry_label(authors_text, rest_text):
    """Label of a printed reference: authors_text is the text before the
    title, rest_text the text after it (where the year is)."""
    return author_year(split_names(authors_text.strip(" ,.")), find_year(rest_text))


def find_year(text):
    """The year of a printed reference: one in parentheses, else the last one
    that is not part of a page range (1709–1715)."""
    candidates = [m for m in YEAR.finditer(text)
                  if not re.match(r"[–-]\d", text[m.end():m.end() + 2]) and not re.search(r"\d[–-]$", text[:m.start()])]
    for m in candidates:
        if text[m.start() - 1:m.start()] == "(" and text[m.end():m.end() + 1] == ")":
            return m.group(1)
    return candidates[-1].group(1) if candidates else ""


def unique(labels):
    """Disambiguate equal labels: Tantau 2025a, Tantau 2025b. labels: {key: label}."""
    counts = {}
    for label in labels.values():
        counts[label] = counts.get(label, 0) + 1
    seen = {}
    result = {}
    for key, label in labels.items():
        if counts[label] > 1:
            seen[label] = seen.get(label, 0) + 1
            label += "abcdefghijklmnopqrstuvwxyz"[seen[label] - 1]
        result[key] = label
    return result
