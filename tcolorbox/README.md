# HTML version of the tcolorbox manual (prototype)

Converts the tcolorbox manual (`doc/latex/tcolorbox`) into HTML pages in the
style of [tikz.dev](https://tikz.dev), intended to live at `tikz.dev/tcolorbox/`.

Unlike the PGF/TikZ and pgfplots manuals on tikz.dev, this does **not** use
lwarp. The tcolorbox manual is built almost entirely from the macros of
tcolorbox's own `documentation` library, so a dedicated converter is simpler
and more robust:

* `convert.py` parses the LaTeX sources directly and maps `docCommand`,
  `docTcbKey`, `dispExample`, `\refKey`, ... onto the HTML structure that the
  tikz.dev pipeline produces (`manualentry`, `entryheadline`, `example`,
  side tables of contents, ...), so tikz.dev's `style.css` and `pgfmanual.js`
  apply unchanged. `assets/tcolorbox.css` adds a few tcolorbox-specific bits.
  Code examples are highlighted, with every documented key, command and
  environment linked to its definition.
* Everything visual becomes an image. `convert.py tex` writes an instrumented
  copy of the manual to `build/tex` in which each visual fragment carries an
  identifier. `tcbhtml.sty` typesets the manual as usual but also ships every
  marked fragment (the compiled part of each example, boxes in running text,
  inline boxes, ...) as an extra PDF page, in context, and logs
  `identifier → page`. `extract_images.py` crops these pages and converts
  them to SVG (MuPDF + svgo) or PNG. Every SVG is checked against a raster
  of the PDF page; SVGs that render differently (MuPDF gets a few shadings
  and soft masks wrong) or are much larger than the PNG fall back to PNG.

## Building

```bash
./build.sh          # full build: LaTeX (2 LuaLaTeX runs) + images + HTML
./build.sh images   # re-extract images from the last LaTeX run, then HTML
./build.sh html     # only regenerate HTML
python3 serve.py    # preview at http://127.0.0.1:8765/tcolorbox/
python3 check_links.py
```

Requires LuaLaTeX, Python 3, `mutool`, `pdfcrop`, `pdftocairo`. Optional:
`svgo` and `pngquant` (smaller files), `rsvg-convert` with numpy and Pillow
(SVG verification; without it, SVGs are used unchecked).

`tcbhtml-compat.sty` lets the repository's tcolorbox run on LaTeX kernels
older than 2025-06-01 by emulating the tagging sockets (only needed until the
TeX installation is updated).

Image identifiers are assigned in source order, so after changing what
`convert.py` treats as an image, the full build has to be rerun.

## Status of the prototype

* All 28 chapters, part pages, references and the home page are generated;
  963 images (948 SVG, 15 PNG; 9.7 MB transferred with gzip vs 26 MB as
  PNG), 0 broken internal links (`check_links.py`).
* Boxes in running text, tables and other "visual prose" become images
  rather than HTML (only examples have their code as text).
* Breakable boxes are captured unbroken (e.g. one long column for an example
  that the PDF splits across columns/pages).
* Two examples using tabularray fail with the TeX Live 2025 tabularray
  (version mismatch with the repository's code); fixed by updating TeX Live.
* No search index, sitemap, or link from the tikz.dev front page yet.
