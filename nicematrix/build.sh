#!/bin/bash
# Build the HTML version of the nicematrix manual into build/site/nicematrix.
#
#   ./build.sh            full build (instrumented LaTeX run + images + HTML)
#   ./build.sh images     only re-extract images from an existing LaTeX run
#   ./build.sh html       only regenerate the HTML pages
#
# Requirements: LuaLaTeX (TeX Live), Python 3, mutool, pdfcrop, pdftocairo,
# Ghostscript, optionally pngquant, svgo, rsvg-convert.
set -euo pipefail
cd "$(dirname "$0")"
HERE=$(pwd)
# the repository at the pinned commit (see ../scripts/fetch.sh)
UPSTREAM=${UPSTREAM:-$HERE/../.upstream/nicematrix}
[[ -f $UPSTREAM/nicematrix.tex ]] || { echo "missing $UPSTREAM, run: scripts/fetch.sh nicematrix" >&2; exit 1; }
export UPSTREAM
TEX="$HERE/build/tex"
IMG="$HERE/build/images"
# compile with the package code of the pinned version, not the one in TeX Live
# nicematrix.sty is generated from nicematrix-code.dtx in build/tex (convert.py tex)
export TEXINPUTS=".:"
STEP=${1:-all}

if [[ $STEP == all ]]; then
  python3 convert.py tex
  cd "$TEX"
  # nicematrix draws rules, delimiters and blocks at cell positions recorded
  # in the .aux file of the previous run; rerun until the positions settle
  # (two runs are not enough), at most five times
  rm -f nicematrix-html.aux
  for run in 1 2 3 4 5; do
    echo "LuaLaTeX run $run ..."
    [[ -f nicematrix-html.aux ]] && cp nicematrix-html.aux previous.aux
    lualatex -interaction=nonstopmode nicematrix-html.tex > "lualatex-run$run.out" 2>&1 < /dev/null || true
    if [[ $run -ge 2 ]] && cmp -s previous.aux nicematrix-html.aux; then break; fi
  done
  grep -c "" nicematrix-html.htmlimages | xargs echo "image fragments logged:"
  cd "$HERE"
fi

if [[ $STEP == all || $STEP == images ]]; then
  python3 ../shared/texhtml/extract_images.py "$TEX/nicematrix-html.pdf" "$TEX/nicematrix-html.htmlimages" "$IMG"
fi

python3 convert.py html
echo "Done: $HERE/build/site/nicematrix"
