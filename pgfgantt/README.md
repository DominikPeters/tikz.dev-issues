# pgfgantt manual

The lwarp build of [pgfgantt](https://github.com/skafdasschaf/latex-pgfgantt)
for `tikz.dev/pgfgantt/`, with the shared navigation, styling and DocSearch
frontend used by the other manuals.

```bash
scripts/fetch.sh pgfgantt
scripts/build.sh pgfgantt
scripts/serve.py          # http://127.0.0.1:8765/pgfgantt/
```

The build runs docstrip to obtain the package matching the pinned documentation.
`preprocess.py` unwraps the `.dtx` documentation into ordinary LaTeX, leaving
all 73 example listings intact and retaining implementation code as 103
verbatim listings. This avoids docstrip's comment catcodes affecting executable
TikZ calculations. The HTML adapter maps key descriptions and command
declarations to the common manual presentation. Related implementation names
become consecutive headings rather than deeply nested lists.

Whole chart examples are captured, including custom link definitions before
the chart: these definitions must be parsed with native math catcodes.
Illustrations use the shared cached PDF conversion and SVG/PNG selection after
SVGO. Examples are executed normally in document order; no drawing reuse audit
is assumed. The command/key index has a separate page.

Requires the same TeX Live, LuaLaTeX, Python and graphics tools as the other
lwarp manuals. The normal build, upstream-watch and deployment workflows
include this package.
