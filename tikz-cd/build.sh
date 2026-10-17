#!/usr/bin/env bash
set -euo pipefail

# Generate lwarp's HTML driver, index style and build configuration without
# typesetting the whole print manual. The published PDF link points to CTAN.
lualatex -interaction=nonstopmode -halt-on-error -jobname=tikz-cd-doc \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{tikz-cd-doc.tex}'
lwarpmk html
python3 convert_illustrations.py tikz-cd-doc_html.pdf tikz-cd-doc-images.txt tikz-cd-doc-images
svgo -f tikz-cd-doc-images
python3 illustration_formats.py tikz-cd-doc_html.pdf tikz-cd-doc-images.txt tikz-cd-doc-images tikz-cd-image-formats.json
python3 postprocessing.py
