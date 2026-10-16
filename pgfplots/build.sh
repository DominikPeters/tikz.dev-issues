#!/bin/bash

# Write lwarp's configuration and HTML driver with a single blank page.
lualatex -shell-escape -interaction=nonstopmode -halt-on-error -jobname=pgfplots \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{pgfplots.tex}' || exit 1
lwarpmk cleanall
# Drawing reuse is limited to reference passes of this build.
rm -rf pgfplots_html.render-cache
rm -f pgfplots_html.render-cache-pending.jsonl pgfplots_html.render-cache-used.jsonl
lwarpmk html || exit 1
# Keep the ImageMagick shader fallbacks used by the HTML postprocessor.
python3 convert_illustrations.py pgfplots_html.pdf pgfplots-images.txt pgfplots-images \
  --magick --allow-missing-end || exit 1
python3 postprocessing.py || exit 1
svgo -f processed/pgfplots-images || exit 1
