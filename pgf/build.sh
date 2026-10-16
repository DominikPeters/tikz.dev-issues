#!/bin/bash

# Write lwarp's configuration and HTML driver with a single blank page.
lualatex -interaction=nonstopmode -halt-on-error -jobname=pgfmanual \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{pgfmanual.tex}' || exit 1
lwarpmk cleanall
lwarpmk html || exit 1
# The converter waits for all workers and fails if any image fails.
./build-limages-with-margin.lua limages || exit 1
python3 postprocessing.py || exit 1
svgo -f processed/pgfmanual-images || exit 1
