#!/bin/bash

lualatex -interaction=nonstopmode -halt-on-error pgfmanual.tex
lwarpmk cleanall
lwarpmk html
./build-limages-with-margin.lua limages
# the image conversions run in the background; each removes its
# lateximagetemp-*.pdf when done. Wait until none is left (checked twice).
busy() { compgen -G "pgfmanual-images/lateximagetemp-*.pdf" >/dev/null || compgen -G "pgfmanual-images/*.tmp" >/dev/null; }
for _ in $(seq 360); do   # at most half an hour
  busy || { sleep 5; busy; } || break
  sleep 5
done
python3 postprocessing.py || exit 1
svgo -f processed/pgfmanual-images || exit 1
