# tcolorbox manual

Converts the tcolorbox manual (`doc/latex/tcolorbox` of
[T-F-S/tcolorbox](https://github.com/T-F-S/tcolorbox), checked out by
`scripts/fetch.sh tcolorbox` into `.upstream/tcolorbox`) into HTML pages in the
style of [tikz.dev](https://tikz.dev), to live at `tikz.dev/tcolorbox/`.

Unlike the PGF/TikZ and pgfplots manuals on tikz.dev, this does **not** use
lwarp. The tcolorbox manual is built almost entirely from the macros of
tcolorbox's own `documentation` library, so a dedicated converter is simpler
and more robust:

* `convert.py` parses the LaTeX sources directly, with the shared converter
  in `../shared/texhtml` (see [docs/converters.md](../docs/converters.md)), and
  maps `docCommand`,
  `docTcbKey`, `dispExample`, `\refKey`, ... onto the HTML structure that the
  tikz.dev pipeline produces (`manualentry`, `entryheadline`, `example`,
  side tables of contents, ...), so the shared `style.css` and `pgfmanual.js`
  in `../shared/` apply (tcolorbox-specific rules there are scoped by
  `.pkg-tcolorbox`).
  Code examples are highlighted, with every documented key, command and
  environment linked to its definition.
* Everything visual becomes an image. `convert.py tex` writes an instrumented
  copy of the manual to `build/tex` in which each visual fragment carries an
  identifier. `tikzdev-capture.sty` (with `tcbhtml.sty` for the examples)
  typesets the manual as usual but also ships every marked fragment (the
  compiled part of each example, boxes in running text, inline boxes, ...) as
  an extra PDF page, in context, and logs `identifier → page`.
  `extract_images.py` crops these pages and converts
  them to SVG (MuPDF + svgo) or PNG. Every SVG is checked against a raster
  of the PDF page; SVGs that render differently (MuPDF gets a few shadings
  and soft masks wrong) or are much larger than the PNG fall back to PNG.

## Building

From the repository root, `scripts/fetch.sh tcolorbox && scripts/build.sh tcolorbox`
does everything. Inside this folder:

```bash
./build.sh          # full build: LaTeX (2 LuaLaTeX runs) + images + HTML
./build.sh images   # re-extract images from the last LaTeX run, then HTML
./build.sh html     # only regenerate HTML
python3 check_links.py
```

To preview, build from the repository root and run `scripts/serve.py`
(<http://127.0.0.1:8765/tcolorbox/>).

Requires LuaLaTeX, Python 3, `mutool`, `pdfcrop`, `pdftocairo`. Optional:
`svgo` and `pngquant` (smaller files), `rsvg-convert` with numpy and Pillow
(SVG verification; without it, SVGs are used unchecked).

`tcbhtml-compat.sty` lets the repository's tcolorbox run on LaTeX kernels
older than 2025-06-01 by emulating the tagging sockets (only needed until the
TeX installation is updated).

Image identifiers are assigned in source order, so after changing what
`convert.py` treats as an image, the full build has to be rerun.

## Known limitations

* Boxes in running text, tables and other "visual prose" become images
  rather than HTML (only examples have their code as text).
* Breakable boxes are captured unbroken (e.g. one long column for an example
  that the PDF splits across columns/pages).
* Two examples using tabularray fail with the TeX Live 2025 tabularray
  (version mismatch with the repository's code); fixed by updating TeX Live.
