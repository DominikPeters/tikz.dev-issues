#!/usr/bin/env bash
set -euo pipefail
lualatex -interaction=nonstopmode -halt-on-error -jobname=wheelchart \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{wheelchart.tex}'
lwarpmk html
python3 convert_illustrations.py wheelchart_html.pdf wheelchart-images.txt wheelchart-images
svgo -f wheelchart-images
python3 illustration_formats.py wheelchart_html.pdf wheelchart-images.txt wheelchart-images wheelchart-image-formats.json
python3 postprocessing.py
