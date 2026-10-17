# PGF illustration format selection

The PGF build now optimizes SVGs before comparing sizes. It selects SVG when
the optimized SVG is no larger than the PNG, subject to PDF feature fallbacks
and the existing manual SVG overrides. PGFplots is unchanged.

## Evidence for the fallbacks

The review used the PGF source pinned at
`1d6234878836bc50b5e5a15ae266d74911466e7a`, the saved full-manual PDF and
illustrations from the cache validation, Poppler 25.03.0, and SVGO 4.1.0.
All 274 illustrations using the surveyed PDF features were rasterized from
SVG with librsvg and compared with the existing PNGs. Representative cases
were also inspected in Chromium, including after SVG optimization.

| Used PDF feature | Observed conversion behavior | Automatic policy |
| --- | --- | --- |
| Knockout transparency groups | The raw SVG of `image-1802` lost the gradient along its border in the browser comparison. | PNG |
| Luminosity masks or mask transfer functions | Poppler samples these into bitmap masks even for SVG output. `image-2381` shows a coarse grid around its faded circle; `image-3371` has a coarse fading edge. | PNG |
| Function shadings (type 1) and mesh shadings (types 4–7) | Cairo uses raster fallbacks. The function-shading example `image-2575` loses detail compared with the 300 dpi PNG. Mesh types are covered by the same raster-fallback rule; none occur in this PGF corpus. | PNG |
| Blend modes beyond Normal, Multiply, Screen, Darken and Lighten | Bitmap fragments can introduce seams and coarse edges, visible in `image-1783` (Luminosity blend). | PNG |
| Ordinary opacity, axial/radial gradients, tiling patterns, image alpha and simple shadows | These features alone do not establish a conversion problem. For example, the offset shadow in `image-2583` remains suitable for SVG. | Smaller file after SVGO |

The scanner follows content operators into forms, patterns and soft masks;
unused entries in a PDF resource dictionary do not trigger a fallback.
For reused drawings, it inspects the saved original page rather than the
PDF import wrapper. The build writes features, risks, byte sizes and choices
to `pgfmanual-image-formats.json`, outside the published image directory.

These are conservative rules for the current Poppler/Cairo conversion path,
not a claim that SVG itself cannot express these effects. Explicit
`codeexample[svg]` overrides and the existing patterns-library exception remain
available for cases where PNG conversion has its own problems. Linked SVG
objects retain their existing behavior for interactivity.

## Corpus results

Of 3,394 unique illustrations, the automatic policy picks 2,289 SVGs and
1,105 PNGs. There are 98 PDF-feature fallbacks: 58 masks, 33 advanced blends,
6 function shadings and 1 knockout group. SVG optimization changes 1,775
otherwise size-driven decisions from PNG to SVG.

After the existing HTML overrides, the actual pages reference 2,330 SVGs
and 1,064 PNGs, versus 59 SVGs and 3,335 PNGs under the old rule. The optimized
files selected by the old rule total 22,545,037 bytes; the new selection totals
17,039,409 bytes, a **24.42% reduction**. This measures the unique illustration
files referenced by the pages, before HTTP compression. Both formats remain
in the generated output directory, so it does not measure deployment size.

## Validation

- All 21 format-policy and conversion-cache tests pass. Cases include unused
  resources, nested/cyclic forms, PDF false booleans, blend alternatives,
  masks, patterns, bitmap alpha, size comparisons, overrides and cached pages.
- Feature/format reports are identical for all 3,394 illustrations in the
  cached and uncached PDFs.
- Full HTML postprocessing completes for all 133 generated pages. Every
  resulting illustration reference matches the independently applied policy,
  and image dimensions are present. This reused existing LaTeX output;
  unrelated official-PDF destination metadata and the upstream update date
  were fixtures because the official PDF download endpoint is unavailable in
  this environment.
- Representative optimized SVGs and selected PNGs were checked in Chromium.
