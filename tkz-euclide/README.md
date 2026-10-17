# tkz-euclide manual

The HTML version of the [tkz-euclide](https://ctan.org/pkg/tkz-euclide)
manual for `tikz.dev/tkz-euclide/`, converted without lwarp with the shared
converter (see [docs/converters.md](../docs/converters.md)).

```bash
scripts/fetch.sh tkz-euclide
scripts/build.sh tkz-euclide
scripts/serve.py          # http://127.0.0.1:8765/tkz-euclide/
```

Inside this folder, `./build.sh images` re-extracts the images of the last
LaTeX run and `./build.sh html` only regenerates the pages.

## Sources

The package comes from CTAN: `upstream.json` pins the CTAN archive by its
checksum (the GitHub repository al-ma-dev/tkz-euclide lags behind CTAN).
CTAN replaces the archive with every release; the build then fails with a
checksum mismatch. To update, download the new archive, put its SHA-256 and
version into `upstream.json`, and the SHA-256 of `upstream.json` into
`upstream.lock`.

The manual is compiled with the package code of the pinned release and the
tkz-doc class and tkzexample package of TeX Live.

## Conversion

The manual uses the tkz-doc class (`TKZdoc-euclide-main.tex` with one file per
chapter):

* each chapter file becomes a page; `\part`s become part pages (`part-...`);
* `NewMacroBox` becomes a command entry like those of the PGF manual; the
  argument and option tables (`\TAline`, `\TOline`) become HTML tables;
* `tkzexample` shows the code next to the picture; the picture is captured by
  `tkzhtml.sty`, which hooks into tkzexample's `\tkz@result`. Examples with
  `code only` and `tkzltxexample` listings have no picture;
* `\tkzcname` links to the command's entry.
