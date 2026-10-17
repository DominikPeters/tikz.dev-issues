#!/usr/bin/env bash
set -euo pipefail

# Generate lwarp's HTML driver, index style and build configuration without
# typesetting the whole print manual. The published PDF link points to CTAN.
lualatex -interaction=nonstopmode -halt-on-error -jobname=tikz-feynman \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{tikz-feynman.tex}'
lwarpmk html
python3 convert_illustrations.py tikz-feynman_html.pdf tikz-feynman-images.txt tikz-feynman-images
svgo -f tikz-feynman-images
python3 illustration_formats.py tikz-feynman_html.pdf tikz-feynman-images.txt tikz-feynman-images tikz-feynman-image-formats.json
python3 postprocessing.py
