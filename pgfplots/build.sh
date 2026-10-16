#!/bin/bash

lualatex -shell-escape -interaction=nonstopmode -halt-on-error pgfplots.tex
lwarpmk cleanall
lwarpmk html
./build-limages-with-margin.lua limages
sleep 10
python3 postprocessing.py
svgo -f processed/pgfplots-images