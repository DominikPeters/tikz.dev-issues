# Drawing reuse and image conversion

Two caches make builds faster without changing their output: reuse of
drawings between the LaTeX passes of one build, and a persistent cache of
converted illustrations.

## Drawing reuse between LaTeX passes

lwarp runs LaTeX several times until references settle. For PGF and PGFplots,
reviewed code examples are drawn in the first pass only; later passes reuse
the PDF page from the first. Setup code, listings, hooks and lwarp's HTML and
reference bookkeeping still run in every pass.

Which examples may be reused is recorded in `<package>/illustration-audit.json`.
An example is reused only if it was reviewed as safe (no labels, remembered
nodes, random numbers, global definitions, file access, shell commands or
other dependencies on state), and only while its source, its chapter and the
prepared source context (other chapters, preambles, helper code) are unchanged
since the review. Anything else is drawn live, as are unreviewed examples and
drawings cheaper than 0.05 CPU seconds.

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
the inventory's file, line and hashes; negative findings win, and anything not
reviewed stays live.

Before committing a new manifest, compare a cached build with an uncached one
(`TIKZ_RENDER_CACHE=0`, with `TIKZ_RENDER_CACHE_MIN_SECONDS=0` for the cached
one so that every reviewed drawing is reused). Use the same `SOURCE_DATE_EPOCH`
for both, and seed Lua's random number generator in both drivers, since its
initial state varies between runs. The HTML, the auxiliary, index and
bibliography files, the image lists and every converted SVG/PNG should match
byte for byte.

## Illustration conversion

The lwarp manuals extract, crop (one-point margin) and convert illustrations
to SVG and 300 dpi PNG in a pool of workers (`TIKZ_IMAGE_JOBS`, default 4).
tcolorbox has its own converter (see [tcolorbox/README.md](../tcolorbox/README.md)).

Results are cached in `build/image-cache` (`TIKZ_IMAGE_CACHE` to change), which
CI restores between builds. An entry is keyed by the PDF page and its resources
(fonts, images), the converter code, its settings and the tool versions; page
numbers, file names and timestamps do not matter. Entries are checked against
their checksums and rebuilt if incomplete. Deleting the folder forces a full
conversion. The cache holds unoptimized SVGs, so SVGO and postprocessing can
change independently.

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
