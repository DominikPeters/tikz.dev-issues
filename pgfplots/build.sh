#!/bin/bash

# Write lwarp's configuration and HTML driver with a single blank page.
lualatex -shell-escape -interaction=nonstopmode -halt-on-error -jobname=pgfplots \
  '\AddToHook{begindocument/end}{\null\clearpage\end{document}}\input{pgfplots.tex}' || exit 1
lwarpmk cleanall
lwarpmk html || exit 1
# The converter waits for all workers and fails if any image fails.
./build-limages-with-margin.lua limages || exit 1
python3 postprocessing.py || exit 1
svgo -f processed/pgfplots-images || exit 1
