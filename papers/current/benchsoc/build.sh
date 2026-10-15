#!/bin/sh
# Build paper.pdf with pdflatex + bibtex (no latexmk on this machine).
# BasicTeX lacks some packages ceurart.cls needs; they were installed into a
# local user tree (gitignored) with:
#   tlmgr init-usertree --usertree "$PWD/texmf"
#   tlmgr --usermode --usertree "$PWD/texmf" install doclicense csquotes moreverb \
#     wrapfig makecell sttools xifthen ifmtarg libertinus libertinus-type1 \
#     libertinus-fonts fontawesome5 fontaxes
# ceurart.cls and elsarticle-num-names.bst are copied from the CEUR-WS
# template (https://ceur-ws.org/Vol-XXX/CEURART.zip).
set -e
cd "$(dirname "$0")"
export TEXMFHOME="$PWD/texmf"
pdflatex -interaction=nonstopmode -halt-on-error paper >/dev/null
bibtex paper || echo "bibtex reported errors (see paper.blg)"
pdflatex -interaction=nonstopmode -halt-on-error paper >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error paper >/dev/null
/usr/bin/grep -E "Output written|LaTeX Warning: (Citation|Reference)" paper.log || true
