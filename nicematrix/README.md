# nicematrix manual

The HTML version of the [nicematrix](https://ctan.org/pkg/nicematrix) manual
for `tikz.dev/nicematrix/`, converted without lwarp with the shared converter
(see [docs/converters.md](../docs/converters.md)).

```bash
scripts/fetch.sh nicematrix
scripts/build.sh nicematrix
scripts/serve.py          # http://127.0.0.1:8765/nicematrix/
```

Inside this folder, `./build.sh images` re-extracts the images of the last
LaTeX run and `./build.sh html` only regenerates the pages. `nicematrix.sty` is
generated from `nicematrix-code.dtx` of the pinned commit. nicematrix requires
a recent LaTeX release (7.12: 2026-06-01 or later) and siunitx.

## Conversion

The manual is `nicematrix.tex`; the documentation of the code
(`nicematrix-code.dtx`) and the French version are not converted.

* every `\section` becomes a page; the introduction goes on the start page and
  the history of changes on a last page. The index is not reproduced, and
  "p. 17" after a reference is dropped;
* `Code` is a piton environment: the listing is shown with the parts marked by
  `\emph` highlighted (and without the `\emph`, as piton does when it runs the
  code). With the key `show-output`, the environment also typesets the code;
  `convert.py tex` patches the manual's definition of `Code` to capture that
  output. Without it, the output is usually typeset separately right after
  the listing (a `minipage`, a `NiceTabular`, ...); that image is shown next
  to the listing;
* `\Definition{key}` and `\DefinitionCommand{name}` become anchors, and the
  keys and commands in the listings link to them (except very common names
  like `color` or `width`);
* the environments of nicematrix, in math or not, are images.
