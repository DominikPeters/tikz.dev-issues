#!/usr/bin/env bash
set -euo pipefail

# Generate lwarp's HTML driver, index style and build configuration without
# typesetting the whole print manual. The published PDF link points to CTAN.
lualatex -interaction=nonstopmode -halt-on-error -jobname=pgf-pie-manual \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{pgf-pie-manual.tex}'
lwarpmk html
python3 convert_illustrations.py pgf-pie-manual_html.pdf pgf-pie-manual-images.txt pgf-pie-manual-images
svgo -f pgf-pie-manual-images
python3 illustration_formats.py pgf-pie-manual_html.pdf pgf-pie-manual-images.txt pgf-pie-manual-images pgf-pie-image-formats.json
python3 postprocessing.py
