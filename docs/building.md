# Building the manuals

## Sources

Each manual pins an upstream revision in `<package>/upstream.lock` (`repo`,
`commit`, the `watch` paths that trigger a rebuild, the documentation folder
`docdir`, and the `sitepath` on tikz.dev). wheelchart, tkz-euclide and chemfig are
fetched from archives instead of Git: their `upstream.json` pins the archives
by checksum (see [wheelchart/README.md](../wheelchart/README.md) and
[tkz-euclide/README.md](../tkz-euclide/README.md)).

```bash
scripts/fetch.sh pgf               # checkout at the pinned commit, in .upstream/pgf
scripts/fetch.sh pgf origin/master # try another revision without changing the pin
scripts/prepare.py pgf             # only assemble the source tree build/pgf/src
scripts/build.sh pgf               # prepare, run LaTeX and postprocessing -> build/pgf/site
```

`prepare.py` copies the upstream tree, runs `<package>/preprocess.py` if there
is one, applies `<package>/patches/`, and adds the package's own files and
`shared/`. Manuals whose lock says `documentation=pgf` (those written with
PGF's documentation macros) also get the HTML versions of those macros from
`shared/pgfmanual/`. LaTeX runs with the package code of the pinned commit
ahead of the version in TeX Live, so the manual describes the code it is
compiled with.

`scripts/build.sh` refuses to publish a site whose LaTeX run failed or that
has no `index.html`. The manuals processed by `shared/pgf_contrib_site.py`
are also checked by `shared/check_manual_site.py` (missing files, broken
anchors, missing image dimensions, unresolved references), as are tcolorbox,
tkz-euclide and chemfig before their sites are published. To check a built
manual directly, run `python3 shared/check_manual_site.py build/<package>/site`.

## Fixing a patch

When upstream changes a place one of the patches touches, the build stops
with "patch X does not apply":

```bash
scripts/fetch.sh pgf <new-commit>
scripts/prepare.py pgf --reject      # applies what it can, leaves *.rej files
# edit the files named by the .rej files in build/pgf/src by hand, then
scripts/prepare.py pgf --refresh-patches build/pgf/src
```

`--refresh-patches` rewrites `pgf/patches/` from the edited tree. Commit it
together with the new commit in `pgf/upstream.lock`.

## Frontend

All manuals use `shared/style.css` and `shared/pgfmanual.js`. Each build sets
a class on `<html>` that selects package-specific rules: `.pkg-pgf`,
`.pkg-pgfplots`, `.pkg-tcolorbox`, and so on. The manuals other than PGF,
PGFplots and tcolorbox also have `.pkg-pgf-contrib` and share their page
processing in `shared/pgf_contrib_site.py`. The list of manuals in the header
menu is in `shared/navbar.py`. Local CSS and JavaScript URLs carry content
hashes, so browsers pick up new versions immediately.

Search uses DocSearch v3 (`shared/docsearch.py`, initialised in
`pgfmanual.js`) with the Algolia application `JS6V5VZSDB` and index `tikz`.
Each manual filters by its own tag (PGF: `tikz`, the others: their package
name). The crawler and index settings are managed in Algolia, not here; a new
manual's search returns results once the crawler has indexed and tagged it.

## lwarp speedups

The lwarp manuals load `shared/tikz-dev-fast-lwarp.sty`, which caches parsed
argument handlers for spans and filename sanitization instead of rebuilding
them for every coloured word and link, and skips one redundant LaTeX pass. If
lwarp changes the code it relies on, it falls back to lwarp's own handler and
logs a warning. `scripts/tests/test_fast_lwarp.py` compares the HTML, references and
image lists with stock lwarp.

## Tests

```bash
python3 -m unittest discover -s scripts/tests
```
