#!/usr/bin/env python3
"""Check internal links of the generated site (build/site/tcolorbox)."""
import os, re, sys, html
from collections import Counter
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "site", "tcolorbox")
ids, hrefs = {}, []
for name in os.listdir(SITE):
    if not name.endswith(".html"):
        continue
    page = name[:-5]
    text = open(os.path.join(SITE, name), encoding="utf-8").read()
    ids[page] = {html.unescape(m) for m in re.findall(r'\bid="([^"]*)"', text)}
    for m in re.findall(r'href="([^"]*)"', text):
        hrefs.append((page, html.unescape(m)))
bad = Counter()
for page, h in hrefs:
    if h.startswith(("http", "mailto", "/")) or h.endswith((".css", ".js")) or "?" in h:
        continue
    target, _, frag = h.partition("#")
    target = target or page
    if target in ("./", ""):
        target = "index"
    if target not in ids:
        bad[f"missing page {target}"] += 1
    elif frag and frag not in ids[target]:
        bad[f"{target}#{frag}"] += 1
print(f"{len(hrefs)} links, {sum(bad.values())} broken")
for k, v in bad.most_common(30):
    print(f"  {v}x {k}")
