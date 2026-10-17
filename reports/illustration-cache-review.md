# Illustration drawing-cache review

Review baseline: monorepo commit `ca754d2`, PGF upstream
`1d6234878836bc50b5e5a15ae266d74911466e7a`, and PGFplots upstream
`f40faa5864936890736461a2b410dcef8968e97f`. The package audit manifests contain
the exact source fingerprints, decisions, and reasons.

Six Luna agents reviewed file-balanced batches, with automatic hazard screening
and additional checks of eligible examples against surrounding definitions and
library implementations. Existing unsafe findings were retained. Automatic
screening never grants eligibility; negative findings override positive ones.

| Decision | PGF | PGFplots |
| --- | ---: | ---: |
| Eligible | 832 | 532 |
| Listing only | 465 | 336 |
| Unsafe | 121 | 137 |
| Uncertain | 323 | 14 |
| Unsupported | 1,116 | 269 |
| Total | 2,857 | 1,288 |

Eligible examples span 61 PGF chapters and 35 PGFplots chapters. Counts refer to
codeexamples, which can contain several pictures. Only complete outer
`tikzpicture` environments are replaced. Inline `\tikz`, raw `pgfpicture`,
adjacent pictures without a blank-line separator, alternate renderers, and existing outer image wrappers keep their original
execution paths.

The review excludes random-state effects, labels and other auxiliary writes,
global declarations, external data and shell execution, remembered nodes, and
uncertain dependencies. Three PGFplots patch-refinement examples also stay live:
an outer loop executes one picture template with different inputs, which a
static source key cannot distinguish. Setup code, pre/post hooks, listings, and
code outside replaced pictures continue executing.

Examples of exclusions retained or found during the cross-checks:

| Prepared source | Reason to execute normally |
| --- | --- |
| PGF `pgfmanual-en-tikz-plots.tex:325` | `plot function` invokes gnuplot and uses generated plot files. |
| PGFplots `pgfplots.reference.axis-addplot.tex:1578,1594` | Shell commands write and read `pgfshell_cos.out`. |
| PGFplots `pgfplots.libs.patchplots.tex:915,956,1002` | Outer refinement loops execute the same rewritten template repeatedly. |
| PGF `pgfmanual-en-tikz-actions.tex:1029,1063,1097,1150` | An existing outer `lateximage` envelope also owns surrounding text. |
| PGF `pgfmanual-en-library-shadows.tex:118` and `pgfmanual-en-library-shapes.tex:933,953,984` | Starburst shapes implicitly advance the global RNG, changing a later random visualization if skipped. |

Shared context matters: edits to another chapter, a preamble, or a TeX/Lua helper
invalidate eligibility even if an example's own source is unchanged. The context
fingerprint is computed from a freshly prepared, untagged documentation tree.
Source review is not a general proof of TeX purity.

Both packages enable drawing reuse. The default minimum drawing CPU time is
0.05 seconds, retaining cheap pictures on the normal path. Correctness validation
sets `TIKZ_RENDER_CACHE_MIN_SECONDS=0` to exercise all reviewed candidates. Runtime
regressions cover normal document catcodes and text immediately following a
picture; cache-end commands use an explicit delimiter.

## Validation

Full-manual validation uses TeX Live 2025, LuaHBTeX 1.22.0, lwarp 0.921, and a
fixed `SOURCE_DATE_EPOCH` per comparison. Cached builds converge through
`lwarpmk html`. A copy of the converged state is rebuilt with
`TIKZ_RENDER_CACHE=0`, then `lwarpmk pdftohtml` regenerates HTML. The PGFplots
pair uses identical `lwarpmk html` commands so shell escape and the `lwarp.ist`
index style match. Its generated validation drivers also seed Lua's RNG to
12345: LuaTeX's initial `math.random` state varies even with a fixed build date.
This leaves intentionally random examples live while making their output
comparable. The seed hook is confined to disposable validation drivers.
Checks compare HTML and extracted PDF text with raw differences retained.
Non-rendered HTML comments are ignored only when the remaining bytes match
exactly: PGFplots' ternary chapter has one fallback-equation comment whose
PDF-extracted fraction text is ordered differently, while its MathJax source is
identical. Auxiliary/index/bibliography files, image manifests, and converted
SVG/PNG files are compared byte for byte. Conversion uses the saved original PDF
pages for cached drawings.

The image comparison caught a genuine indirect state effect: deterministic-looking
starburst shapes seed and advance PGF's global RNG internally. Their images
matched, but skipping them changed the later, uncached random visualization at
the start of the Data Visualization part. These four examples now execute
normally. `SOURCE_DATE_EPOCH` and `FORCE_SOURCE_DATE=1` already fix PGF's initial
time-based seed; adding another initial seed would not repair omitted RNG
advances.

Both final full-manual comparisons pass:

| Check | PGF | PGFplots |
| --- | ---: | ---: |
| Reused picture payloads | 828 | 549 |
| Generated HTML files compared | 141 | 82 |
| Identical SVG/PNG outputs | 6,788 | 3,309 |
| Auxiliary/index/bibliography state and image manifests | Exact match | Exact match |
| HTML and PDF-extracted text | Exact match | Match outside the documented comment |

Five eligible examples are not executed by these manuals: three in PGF's unused
`dv-examples` source, one inside `\iffalse` in PGF's perspective chapter, and one inside `\iffalse` in PGFplots'
Smith-chart chapter. Their source was reviewed, but these builds do not validate
their runtime behavior.

The test suite passes all 52 tests, including cache replay versus stock lwarp,
high-threshold live rendering, invalid threshold diagnostics, stale review
contexts, negative review precedence, and external/loop/wrapper screening.

The default-threshold experiment starts with converged references and an empty
drawing cache. Its first pass draws every picture; its second pass includes
original-page extraction and reuses only pictures exceeding 0.05 CPU seconds.
Times below include the engine wrapper and its child processes, measured once
per pass on this machine. HTML extraction and illustration conversion are
measured separately and are excluded from these rendering CPU times.

| Manual | Live pass CPU seconds | Reuse pass CPU seconds | CPU reduction | Drawings reused |
| --- | ---: | ---: | ---: | ---: |
| PGF | 366.5 | 355.5 | 3.0% | 149 |
| PGFplots | 300.9 | 243.8 | 19.0% | 380 |

Both passes match the reference HTML/text under the comparison rules above, and
all auxiliary/index/bibliography state and image manifests match exactly. Both
default-policy converted-image comparisons also pass: all 10,097 SVG/PNG files
match the uncached references byte for byte.

These are controlled reference-pass CPU measurements, including initial cache
extraction overhead. They are not a cold-build or wall-time speedup claim.
Multipass convergence and one uncached reference pass have different scopes and
must not be compared as though they were the same workflow.
