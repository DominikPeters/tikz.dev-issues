#!/usr/bin/env bash
set -euo pipefail
lualatex -interaction=nonstopmode -halt-on-error pgfgantt.ins
lualatex -interaction=nonstopmode -halt-on-error -jobname=pgfgantt-manual \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{pgfgantt-manual.tex}'
lwarpmk html
python3 convert_illustrations.py pgfgantt-manual_html.pdf pgfgantt-manual-images.txt pgfgantt-manual-images
svgo -f pgfgantt-manual-images
python3 illustration_formats.py pgfgantt-manual_html.pdf pgfgantt-manual-images.txt pgfgantt-manual-images pgfgantt-image-formats.json
python3 postprocessing.py
