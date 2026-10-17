# tikz-cd manual

The lwarp build of [tikz-cd](https://github.com/astoff/tikz-cd) for
`tikz.dev/tikz-cd/`. Its upstream manual uses PGF's documentation macros, so
it shares the HTML documentation helpers in `shared/pgfmanual/` with PGF.

From the repository root:

```bash
scripts/fetch.sh tikz-cd
scripts/build.sh tikz-cd
python3 -m http.server --directory build/tikz-cd/site 8765
```

Open <http://localhost:8765/> to preview this manual. Cross-manual links need
the sibling manuals at their deployed paths. The build uses the PGF supplied
by TeX Live and does not require a PGF manual build, PDF download, or network
access after the upstream checkout and tools are installed.

Requires LuaLaTeX, lwarp, latexmk, Python with BeautifulSoup/html5lib and pypdf,
Poppler, Ghostscript, pdfcrop, pngquant, and SVGO (as installed by the shared
build workflow). `patches/tikz-cd-doc.tex.patch` adapts the upstream preamble,
marks its table-building macros for lwarp, assigns stable page names, and
turns references to numbered PGF sections into relative semantic HTML links.
`tikz-cd-html.sty` adapts function-name anchors containing underscores.

The build generates five pages, including all 31 examples, 47 documentation
blocks, 13 tables and the index. It converts all 86 illustrations through the
shared persistent image cache, runs SVGO, and applies the shared PDF-feature
and size policy. Unreviewed drawings execute on every LaTeX pass.

`postprocessing.py` adds the package menu, responsive navigation, section and
definition permalinks, copy buttons, image dimensions, and the shared MathJax
configuration. `check_manual_site.py` rejects missing local files, broken
anchors, duplicate ids, missing image dimensions and unresolved reference
markers before `scripts/build.sh` publishes the local build result. A changed
set of upstream main sections fails explicitly until the page map is reviewed.

The package lock participates in upstream watching; the shared build and
artifact-deployment workflows recognize it. Publishing still uses the normal
deployment workflow and `/tikz-cd/` site path.
