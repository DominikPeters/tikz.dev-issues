# tikz-cd: feasibility of an HTML manual

## Recommendation

Use lwarp with the existing PGF documentation helpers. A dedicated Python
converter is possible, but is not strongly preferred for this manual. Unlike
tcolorbox, tikz-cd already uses the same PGF documentation vocabulary that our
lwarp pipeline supports: `codeexample`, `key`, `stylekey`, `command`,
`pgfmanualentry`, and related environments.

This conclusion is backed by a full-manual conversion probe, not just a small
diagram test. The initial probe produces raw lwarp HTML. The subsequent
integration is described below; publishing uses the normal deployment workflow.

## Upstream and structure

- Repository: <https://github.com/astoff/tikz-cd>.
- Fetched commit: `ca0b856c01c1205abc58985e09c656e944b0b4b1`
  (2022-09-24, upstream HEAD at inspection).
- Package/manual version: 1.0; the manual's title page dates it May 4, 2021.
- Local checkout: `.upstream/tikz-cd`, excluded from version control.
- Sources are at the repository root: `tikz-cd-doc.tex`, `tikz-cd.sty`, and
  `tikzlibrarycd.code.tex`.
- The manual is one 1,446-line file with four main sections and 31 codeexamples.
  It explicitly requires `pgfmanual-en-macros.tex` and optionally imports the
  PGF manual's auxiliary labels for external references.

`tikzcd` ultimately opens a TikZ picture. Lwarp's existing TikZ support captures
it without a dedicated tikz-cd shim. Ordinary diagrams, labels, crossing arrows,
custom paths, font-dependent arrow tips, and the standalone shape illustration
all compile in the probe.

## What the probe needed

The probe reuses the six existing `pgf/pgfmanual*` TeX helper files and the shared
fast-lwarp package. It uses the monorepo's pinned PGF sources, LuaLaTeX from
TeX Live 2025, and lwarp 0.921. The manual also builds as a normal PDF.

The compatibility changes are localized:

1. Load lwarp and its usual CSS, MathJax and page-splitting configuration.
2. Pass `nomulticol,nohyperref` to `doc` before loading `ltxdoc`. This avoids
   clashes between its automatic package loading and lwarp's replacements.
3. Omit the obsolete PDF-only `hyperref` option `pagecolor` and the two
   print-layout `\raggedcolumns` commands.
4. Surround the definitions of `\displayarrow` and `\displayarrowstyle` with
   lwarp's public `\StartDefiningTabulars` / `\StopDefiningTabulars`. These
   macros expand to table cells; their ampersands must have HTML table catcodes.
   The tables remain HTML text with individual arrow illustrations.
5. Sanitize escaped underscores when the reused PGF `math-function` helper
   constructs anchors for `axis_height` and `rule_thickness`. Otherwise its
   auxiliary labels contain expanded font commands and fail when read back.
6. Set lwarp's `IndexRef=nameref`, so the index links show section names instead
   of invoking undefined cleveref formats for the `pgfmanualentry` counter.
7. Supply the seven referenced PGF labels. The probe extracts their real label
   records from the previously built PGF manual and imports them through `xr`;
   no reference values are fabricated.

There are no patches to the tikz-cd implementation or to the example bodies.
The existing shared illustration converter handles the resulting manifest
unchanged. The format-analysis CLI also accepts it unchanged, after SVGO.

## Results

The completed probe contains:

- Five HTML pages: introduction/home plus the four main sections.
- All 31 codeexamples, 47 documentation blocks and 13 HTML tables.
- 86 illustrations, all successfully converted to SVG and PNG. Conversion took
  2.7 seconds on this workspace, excluding LaTeX compilation and SVGO.
- An index with 204 accepted source records and 141 resulting index items.
- No `??` reference markers, missing image files, or broken local file/anchor
  links in the generated pages.
- All 86 optimized SVGs successfully rasterized with librsvg and contain
  visible content; representative diagrams, arrow tips and the shape example
  were visually inspected.
- No risky PDF features detected by the new image-format scanner. Comparing
  optimized sizes would select 54 SVGs and 32 PNGs. The raw probe pages still
  reference SVGs; applying format choices belongs in the eventual postprocessor.

This establishes feasibility, not pixel-for-pixel equivalence with every
illustration in the printed manual. The remaining LaTeX warnings concern the
existing PGF regex and an unavailable italic small-caps font shape, rather than
unresolved references or compilation failures.

Local probe artifacts are under `/workspace/scratch/tikz-cd-feasibility/`:
`lwarp/` contains the driver, helpers, HTML, image manifest, rendered images
and logs; `pdf/` contains the normal PDF build; `source.patch` records the
manual-source changes; `html-check.json` and `image-formats.json` record checks.
The exploratory passes named `run-1` through `run-10` include intermediate
failures; `lwarp/run-11.out` is the successful final pass.

## Integration work still needed

Factor the PGF HTML documentation helpers into a shared layer rather than copy
them into another package. Add a tikz-cd build wrapper and postprocessor for
stable lowercase page names, navigation, shared site styling, MathJax setup,
image dimensions and format selection. Use stable HTML links for references
to the main PGF manual, and define how its label data and PGF version are made
available in an independent tikz-cd build. Finally add the package pin, package
menu entry, CI/upstream-watch selection and deployment path.

A Python approach would also need much of that integration, plus support for
PGF documentation entries, syntax highlighting and linking, computed separation
tables (`\printsep`), macro-generated arrow tables and in-context example
execution. Those costs have no clear payoff here, given the successful lwarp
probe and the small manual size.

## Implemented integration

`scripts/fetch.sh tikz-cd && scripts/build.sh tikz-cd` now produces the manual
in `build/tikz-cd/site`. The six PGF documentation helpers have moved, with
identical contents, into `shared/pgfmanual/`; selective preparation keeps
PGFplots' variants separate. Both existing audits still enable exactly 832
PGF and 532 PGFplots drawings with no stale records.

The independent build uses TeX Live's PGF and semantic links to the main PGF
manual, so it needs no cross-package build artifacts or external PDF download.
It produces five pages, 31 examples, 47 documentation blocks, 13 tables, the
141-item index, and all 86 illustrations. After SVGO, the size policy selects
54 SVGs and 32 PNGs. Generated pages have package navigation, responsive side
menus, permalinks, copy buttons, MathJax and image dimensions. Build validation
rejects missing files, missing anchors, duplicate ids, unresolved references,
and unexpected new pages that would otherwise be omitted.

The package pin, upstream-watch paths, build selection, artifact deployment
and shared package menus include tikz-cd. No server upload was needed for local
validation. All seven semantic PGF link targets match the saved PGF manual.

Chromium checks covered all five pages, visible SVG/PNG images, MathJax without
TeX errors, the mobile contents menu, copyable example text, and a 390-pixel
viewport without horizontal overflow. Browser tests supplied the exact MathJax
3.2.2 distribution locally because Chromium's certificate store is read-only
in this workspace; generated pages retain the normal shared CDN configuration.
The production build does not depend on those browser-test fixtures.

The full 73-test suite passes, including TeX/cache integration tests and new
site/preparation regressions. A fresh source preparation and full tikz-cd build
succeeds; its warm conversion restores all 86 illustrations in 0.1 seconds.
All 31 example bodies and options match upstream exactly. Build-selection
workflow checks cover six cases, including new-package-only changes and a
shared-file change selecting all four manuals. Wide tables scroll within the
page, and long bibliography URLs wrap on phones.
