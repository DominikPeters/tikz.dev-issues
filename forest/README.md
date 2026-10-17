# forest manual

The HTML version of the [forest](https://ctan.org/pkg/forest) manual for
`tikz.dev/forest/`, converted without lwarp with the shared converter (see
[docs/converters.md](../docs/converters.md)).

```bash
scripts/fetch.sh forest
scripts/build.sh forest
scripts/serve.py          # http://127.0.0.1:8765/forest/
```

Inside this folder, `./build.sh images` re-extracts the images of the last
LaTeX run and `./build.sh html` only regenerates the pages. The package files
(`forest.sty`, `forest-index.sty`, ...) are generated from the `.dtx` sources of
the pinned commit.

## Conversion

The manual is `forest-doc.tex`, with the documentation of the libraries
(`forest-libs.dtx`) and of `forest-index.dtx` included with `\DocInput`; the
converter unwraps these into the text (comment characters removed, code as
listings), for both the pages and the LaTeX run.

* every `\subsection` (and `\librarysection`) becomes a page, every `\section`
  a part;
* `forestexample` shows the code next to the tree, which `forhtml.sty`
  captures; the examples are numbered as in the PDF, so that references like
  "example (6)" work; `forest` environments in running text become images;
* `\index{option>calign}`, `\index{calign}` and the like print a name in a
  style that depends on its category and link it to its definition. The LaTeX
  run logs the printed form of every such call (`forhtml.sty`), and the
  converter turns it into HTML, links included; `\indexitem` in a `syntax`
  environment becomes an entry with the category and default value. The index
  at the end of the PDF is not reproduced.

The manual is compiled with LuaLaTeX (for the image capture), without forest's
externalization, and with `\pdfstrcmp` taken from `pdftexcmds`.
