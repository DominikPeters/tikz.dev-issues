#!/bin/bash

lualatex -shell-escape -interaction=nonstopmode -halt-on-error pgfplots.tex
lwarpmk cleanall
lwarpmk html
./build-limages-with-margin.lua limages
# the image conversions run in the background; each removes its
# lateximagetemp-*.pdf when done. Wait until none is left (checked twice).
busy() { compgen -G "pgfplots-images/lateximagetemp-*.pdf" >/dev/null || compgen -G "pgfplots-images/*.tmp" >/dev/null; }
for _ in $(seq 360); do   # at most half an hour
  busy || { sleep 5; busy; } || break
  sleep 5
done
python3 postprocessing.py || exit 1
svgo -f processed/pgfplots-images || exit 1
