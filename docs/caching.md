# Build caches

Three caches avoid repeated work: reuse of drawings between LaTeX passes,
persistent illustration conversion, and reuse of compiled manuals when only
the frontend changes. Drawing reuse requires source review; the other two
caches use content fingerprints and do not require an example to be reviewed.

## Frontend-only builds

`scripts/build.sh <package>` saves the compiled inputs in
`build/compiled-cache/<package>` after a successful build. With the same native
inputs, the next build restores those inputs and runs only HTML postprocessing
and site checks. CSS, JavaScript, navbar, search, page-shell and package
`postprocessing.py` changes take this path, skipping LaTeX and image conversion.
Python converters restore both the captured images and the LaTeX auxiliary
files used to resolve references and indexes.

The key includes the upstream revision, package patches and TeX helpers,
converter and build code, review manifests, relevant environment settings,
tool versions, the TeX Live package database, local TeX trees and system fonts.
Of the Python modules in `shared/`, only those the manual uses count (its own
scripts' imports, those of the build pipeline, and theirs; see
`scripts/dependencies.py`): an edit to the converters' `texhtml` does not
rebuild PGF. The same rule picks the manuals CI builds after a push: a shared
module rebuilds only the manuals that use it, other changes to `shared/`,
`scripts/` or the workflows rebuild all of them.
Changes to these inputs require a full build. Python `convert.py` files mix
capture and HTML logic, so edits to them also require a full build. Modified
Git checkouts used directly by Python converters and custom `TEXINPUTS` or
`LUAINPUTS` disable compiled reuse. Edits to a disposable prepared tree are not
inputs; use patches or package files instead.

CI restores this cache between runs. It sets `SOURCE_DATE_EPOCH` to the upstream
commit date (archive release date for archive sources) and `FORCE_SOURCE_DATE=1`
so TeX's date remains reproducible across builds. Local builds without a forced
epoch include today's UTC date in the key and rebuild on the next day.

Set `TIKZ_COMPILED_CACHE_ENABLED=0` to force a full native build, or
`TIKZ_COMPILED_CACHE` to change the cache directory. Entries are checksummed;
missing or damaged entries fall back to a full build. Only the two most recent
compiled snapshots per package are retained. Deleting the cache is safe.

## Drawing reuse between LaTeX passes

lwarp runs LaTeX several times until references settle. For PGF and PGFplots,
reviewed code examples are drawn in the first pass only; later passes reuse
the PDF page from the first. Setup code, listings, hooks and lwarp's HTML and
reference bookkeeping still run in every pass.

Which examples may be reused is recorded in `<package>/illustration-audit.json`.
An example is reused only if it was reviewed as safe (no labels, remembered
nodes, random numbers, global definitions, file access, shell commands or
other dependencies on state). Its exact example source and occurrence in the
file must still match the review. The prepared context (other chapters,
preambles, helpers) and package implementation must also match, except that
comments outside executable environments and edits within plain prose
paragraphs may change. Line shifts alone do not invalidate approvals.

This is deliberately conservative: formatted prose containing TeX commands,
headings, macro arguments and unknown environments remain exact. Any change
to executable examples, setup or package code invalidates the context and
keeps the drawings live until reviewed again. Unreviewed examples and drawings
cheaper than 0.05 CPU seconds also stay live. No edit automatically grants a new
approval.

Environment variables:

* `TIKZ_RENDER_CACHE=0` disables the reuse, for comparisons.
* `TIKZ_RENDER_CACHE_MIN_SECONDS` sets the cost threshold (`0` reuses every
  reviewed drawing, useful for checking correctness).

The cache lives in the prepared tree and is cleared at the start of each build.
It saves about 3% of the LaTeX CPU time for PGF and 19% for PGFplots.

Some dependencies are easy to miss. Examples that must stay live: starburst
shapes (they advance PGF's global random number generator, which changes a
later random picture if they are skipped), `plot function` (runs gnuplot),
examples running shell commands, and loops that run one picture template with
different inputs. Only complete outer `tikzpicture` environments are reused;
inline `\tikz`, raw `pgfpicture` and pictures inside an existing image wrapper
always run.

### Reviewing examples

Generate an inventory from a freshly prepared, untagged tree:

```bash
python3 scripts/prepare.py pgfplots --no-illustration-cache --dest build/pgfplots/review
python3 scripts/illustration_audit.py pgfplots build/pgfplots/review/doc/latex/pgfplots \
  --output build/pgfplots/illustration-inventory.json
```

The hazard hints in the inventory are prompts for review, not proof of safety.
Merge review results into a manifest with `--review` (repeatable),
`--manifest-output` and `--upstream-commit`. Every review record must match
the inventory's file, line, ordinal and hashes; copy its `context_policy`,
`context_sha256` and `implementation_sha256` into the review JSON. Negative
findings win, and anything not reviewed stays live. Use `--source-root` if the
prepared documentation path does not end in the lock file's `docdir`.

The PGF and PGFplots manifests use format 2 (`tex-prose-v1`). A legacy manifest
can be migrated without changing its decisions only at its exact original
prepared source and reviewed upstream commit:

```bash
python3 scripts/illustration_audit.py pgfplots build/pgfplots/review/doc/latex/pgfplots \
  --upgrade-manifest pgfplots/illustration-audit.json \
  --upstream-commit <full-reviewed-commit> \
  --manifest-output build/pgfplots/migrated-audit.json
```

Migration refuses stale sources. Legacy manifests otherwise keep their exact
file/context/upstream matching behavior.

Before committing a new manifest, compare a cached build with an uncached one
(`TIKZ_RENDER_CACHE=0`, with `TIKZ_RENDER_CACHE_MIN_SECONDS=0` for the cached
one so that every reviewed drawing is reused). Disable compiled reuse with
`TIKZ_COMPILED_CACHE_ENABLED=0`. Use the same `SOURCE_DATE_EPOCH` and
`FORCE_SOURCE_DATE=1` for both, and seed Lua's random number generator in both
drivers, since its initial state varies between runs. The HTML, the auxiliary, index and
bibliography files, the image lists and every converted SVG/PNG should match
byte for byte.

## Illustration conversion

The lwarp manuals extract, crop (one-point margin) and convert illustrations
to SVG and 300 dpi PNG in a pool of workers (`TIKZ_IMAGE_JOBS`, default 4).
The Python manuals (tcolorbox, tkz-euclide, chemfig, forest, nicematrix) use the
shared `texhtml/extract_images.py` pipeline: missing pages are batched through
MuPDF, pdfcrop and pdftocairo, with SVG verification before format selection.

Results are cached in `build/image-cache` (`TIKZ_IMAGE_CACHE` to change), which
CI restores between builds. An entry is keyed by the PDF page and its resources
(fonts, images), the converter code, its settings and the tool versions; page
numbers, file names and timestamps do not matter. Entries are checked against
their checksums and rebuilt if incomplete. Deleting the folder forces a full
conversion. Identical pages can reuse results after renaming or renumbering;
empty Python captures are cached without publishing placeholder images.
Python conversion stages a complete image directory before replacing the old
one, so a failed conversion leaves the published images intact.

The lwarp cache holds unoptimized SVGs, so SVGO and postprocessing can change
independently. The Python cache (`build/image-cache/texhtml`) includes optimized
SVGs and the verification/format decision; optimizer and verifier versions are
therefore part of its key. Resource changes, including shared font subsets,
still cause conversion misses even when the page's drawing operators match.

To rerun only the conversion on an existing prepared tree:

```bash
cd build/pgf/src/doc/generic/pgf
python3 convert_illustrations.py pgfmanual_html.pdf pgfmanual-images.txt pgfmanual-images \
  --cache ../../../../../image-cache
```

## SVG or PNG

For PGF and the other lwarp manuals except PGFplots, the format is chosen after
SVGO: SVG when it is no larger than the PNG, except for PDF features that
convert poorly with Poppler/Cairo, which always use PNG:

* knockout groups (the gradient along a border gets lost),
* luminosity masks and mask transfer functions (sampled into coarse bitmaps),
* function and mesh shadings (raster fallbacks with less detail than the PNG),
* blend modes other than Normal, Multiply, Screen, Darken and Lighten (seams).

Ordinary opacity, axial and radial gradients, patterns and simple shadows are
fine as SVG. The scanner follows the content actually drawn, into forms,
patterns and masks. Explicit `codeexample[svg]` choices and interactive SVGs
are kept. Each build writes the decisions and reasons to
`pgfmanual-image-formats.json`. For PGF this picks SVG for about two thirds of
the illustrations and saves about a quarter of the image bytes compared with
choosing by unoptimized size. PGFplots keeps its own policy.
