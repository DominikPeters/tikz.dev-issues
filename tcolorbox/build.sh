#!/bin/bash
# Build the HTML version of the tcolorbox manual into build/site/tcolorbox.
#
#   ./build.sh            full build (instrumented LaTeX run + images + HTML)
#   ./build.sh images     only re-extract images from an existing LaTeX run
#   ./build.sh html       only regenerate the HTML pages
#
# Requirements: LuaLaTeX (TeX Live), Python 3, mutool, pdfcrop, pdftocairo,
# optionally pngquant and svgo.
set -euo pipefail
cd "$(dirname "$0")"
HERE=$(pwd)
# upstream checkout at the pinned commit (see ../scripts/fetch.sh)
UPSTREAM=${UPSTREAM:-$HERE/../.upstream/tcolorbox}
[[ -d $UPSTREAM/doc/latex/tcolorbox ]] || { echo "missing $UPSTREAM, run: scripts/fetch.sh tcolorbox" >&2; exit 1; }
export UPSTREAM
TEX="$HERE/build/tex"
IMG="$HERE/build/images"
# Use the tcolorbox code of the upstream checkout, not the one of the TeX distribution.
# The wrapper tcolorbox.sty in build/shim first loads tcbhtml-compat.sty, which
# lets tcolorbox >= 6.9 run on older LaTeX kernels; it is found first also by
# the sub-compilations started from the manual (run pdflatex, ...).
mkdir -p "$HERE/build/shim"
cp "$HERE/tcbhtml-compat.sty" "$HERE/build/shim/"
printf '\\RequirePackage{tcbhtml-compat}\n\\input{%s/tcolorbox.sty}\n' "$(cd "$UPSTREAM/tex/latex/tcolorbox" && pwd)" \
  > "$HERE/build/shim/tcolorbox.sty"
export TEXINPUTS="$HERE/build/shim:$UPSTREAM/tex//:"
STEP=${1:-all}

if [[ $STEP == all ]]; then
  python3 convert.py tex
  cd "$TEX"
  for run in 1 2; do
    echo "LuaLaTeX run $run (this takes a while) ..."
    lualatex -shell-escape -interaction=nonstopmode tcolorbox-html.tex > "lualatex-run$run.out" 2>&1 < /dev/null || true
  done
  grep -c "" tcolorbox-html.htmlimages | xargs echo "image fragments logged:"
  cd "$HERE"
fi

if [[ $STEP == all || $STEP == images ]]; then
  python3 extract_images.py "$TEX/tcolorbox-html.pdf" "$TEX/tcolorbox-html.htmlimages" "$IMG"
  # cover page from the official PDF
  pdftocairo -png -r 60 -f 1 -l 1 -singlefile "$UPSTREAM/doc/latex/tcolorbox/tcolorbox.pdf" "$IMG/cover"
fi

python3 convert.py html
echo "Done. Preview with: python3 serve.py  (http://127.0.0.1:8765/tcolorbox/)"
