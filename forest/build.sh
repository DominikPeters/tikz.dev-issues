#!/bin/bash
# Build the HTML version of the forest manual into build/site/forest.
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
# the CTAN package at the pinned version (see ../scripts/fetch.sh)
UPSTREAM=${UPSTREAM:-$HERE/../.upstream/forest}
[[ -f $UPSTREAM/forest-doc.tex ]] || { echo "missing $UPSTREAM, run: scripts/fetch.sh forest" >&2; exit 1; }
export UPSTREAM
TEX="$HERE/build/tex"
IMG="$HERE/build/images"
# compile with the package code of the pinned version, not the one in TeX Live
# forest.sty etc. are generated from the .dtx files in build/tex (convert.py tex)
export TEXINPUTS=".:"
STEP=${1:-all}

if [[ $STEP == all ]]; then
  python3 convert.py tex
  cd "$TEX"
  for run in 1 2; do
    echo "LuaLaTeX run $run ..."
    lualatex -interaction=nonstopmode forest-doc-html.tex > "lualatex-run$run.out" 2>&1 < /dev/null || true
  done
  grep -c "" forest-doc-html.htmlimages | xargs echo "image fragments logged:"
  cd "$HERE"
fi

if [[ $STEP == all || $STEP == images ]]; then
  python3 ../shared/texhtml/extract_images.py "$TEX/forest-doc-html.pdf" "$TEX/forest-doc-html.htmlimages" "$IMG"
fi

python3 convert.py html
echo "Done: $HERE/build/site/forest"
