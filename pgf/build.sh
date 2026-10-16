#!/bin/bash

# Write lwarp's configuration and HTML driver with a single blank page.
lualatex -interaction=nonstopmode -halt-on-error -jobname=pgfmanual \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{pgfmanual.tex}' || exit 1
lwarpmk cleanall
# Drawing reuse is limited to reference passes of this build.
rm -rf pgfmanual_html.render-cache
rm -f pgfmanual_html.render-cache-pending.jsonl pgfmanual_html.render-cache-used.jsonl
lwarpmk html || exit 1
# Batch extraction/cropping and reuse content-addressed rendered illustrations.
python3 convert_illustrations.py pgfmanual_html.pdf pgfmanual-images.txt pgfmanual-images || exit 1
python3 postprocessing.py || exit 1
svgo -f processed/pgfmanual-images || exit 1
