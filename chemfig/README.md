# chemfig manual

The HTML version of the [chemfig](https://ctan.org/pkg/chemfig) manual for
`tikz.dev/chemfig/`, converted without lwarp with the shared converter (see
[docs/converters.md](../docs/converters.md)).

```bash
scripts/fetch.sh chemfig
scripts/build.sh chemfig
scripts/serve.py          # http://127.0.0.1:8765/chemfig/
```

Inside this folder, `./build.sh images` re-extracts the images of the last
LaTeX run and `./build.sh html` only regenerates the pages.

## Sources

chemfig has no public repository: `upstream.json` pins the CTAN archive by
its checksum. CTAN replaces the archive with every release; the build then
fails with a checksum mismatch. To update, download the new archive, put its
SHA-256 and version into `upstream.json`, and the SHA-256 of `upstream.json`
into `upstream.lock`.

## Conversion

The manual is one file, `chemfig-en.tex`:

* every `\section` becomes a page, numbered within its part as in the PDF; a
  part's introduction, and parts without sections (List of commands,
  Gallery), get a page of their own;
* `\exemple{title}|code|` shows the code next to the molecule; the molecule
  is captured by `chemhtml.sty`, which redefines the last step of `\exemple`;
* molecules and reaction schemes in running text and in tables (`\chemfig`,
  `\schemestart` ... `\schemestop`, `\hreac` ... `\endhreac`, ...) become
  images;
* the key tables print each key's default value (`\CFparam`), which the
  converter reads from the `\setKVdefault` lists in `chemfig.tex`;
* the change history (`changelog.tex`, in French) is the last page.
