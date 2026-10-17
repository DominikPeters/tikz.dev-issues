# pgf-pie manual

The lwarp build of [pgf-pie](https://github.com/pgf-tikz/pgf-pie) for
`tikz.dev/pgf-pie/`, using the shared PGF documentation helpers and contributed
manual page processor.

From the repository root:

```bash
scripts/fetch.sh pgf-pie
scripts/build.sh pgf-pie
python3 -m http.server --directory build/pgf-pie/site 8765
```

Requires the same LuaLaTeX, lwarp, Python, illustration conversion and SVGO
tools as [tikz-cd](../tikz-cd/README.md). Package code comes from the pinned
upstream checkout. No other manual needs to be built first.

The patch loads lwarp, assigns stable page names, and replaces the upstream
print-only example boxing with the shared responsive renderer. All 17 example
files remain unchanged. The upstream Examples section is empty; its page is
retained to preserve the manual's structure. The CTAN upload description
(`description.html`) is excluded from the generated site.

Illustrations use the shared persistent conversion cache and SVG/PNG selection
after SVGO. The page processor adds navigation, code copying, permalinks,
image dimensions and reference validation. The lock participates in the normal
build, upstream-watch and deployment workflows.
