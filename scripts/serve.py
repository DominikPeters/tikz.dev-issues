#!/usr/bin/env python3
"""Preview the built manuals at their tikz.dev paths.

    scripts/serve.py [port]      # http://127.0.0.1:8765/, /pgfplots/, /tikz-cd/, ...

Serves build/<package>/site for each manual that has been built, at the
sitepath from its upstream.lock, and like tikz.dev answers /page with
page.html, so links between pages and manuals work as on the site.
"""
import http.server
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sites():
    found = {}
    for lock in ROOT.glob("*/upstream.lock"):
        values = dict(line.split("=", 1) for line in lock.read_text().splitlines()
                      if "=" in line and not line.startswith("#"))
        site = ROOT / "build" / lock.parent.name / "site"
        if site.is_dir():
            found[values["sitepath"].strip()] = site
    return dict(sorted(found.items(), key=lambda item: -len(item[0])))  # longest path first


SITES = sites()


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        for prefix, site in SITES.items():
            if path.startswith(prefix) or path + "/" == prefix:
                local = site / path[len(prefix):].lstrip("/")
                if local.is_dir():
                    local /= "index.html"
                if not local.exists() and local.with_name(local.name + ".html").exists():
                    local = local.with_name(local.name + ".html")
                return str(local)
        return str(ROOT / "build" / "nonexistent")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    if not SITES:
        sys.exit("No built manuals in build/*/site; run scripts/build.sh <package> first.")
    for prefix, site in reversed(list(SITES.items())):
        print(f"http://127.0.0.1:{port}{prefix}  ->  {site.relative_to(ROOT)}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
