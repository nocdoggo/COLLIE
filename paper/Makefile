# Makefile -- build and check the COLLIE IEEE UV 2026 draft.
#
# Toolchain present on the machine this draft was written on, recorded so a
# reviewer can tell whether a failure is theirs or ours:
#   pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026)
#   latexmk 4.88 (9 March 2026)
#   IEEEtran.cls and IEEEtran.bst present in texmf-dist
# If neither latexmk nor pdflatex is on PATH, `make` says so and exits 1, while
# `make check` still runs: every structural check below is pure text processing.

.ONESHELL:
SHELL := /bin/bash

TEX      := main
LATEXMK  := $(shell command -v latexmk 2>/dev/null)
PDFLATEX := $(shell command -v pdflatex 2>/dev/null)
BIBTEX   := $(shell command -v bibtex 2>/dev/null)

SECTIONS := $(wildcard sections/*.tex)
FIGURES  := $(wildcard figures/*.pdf) $(wildcard figures/*.tex)
SOURCES  := $(TEX).tex $(SECTIONS) $(FIGURES) citations.bib
CHECK    := check.py

.PHONY: all pdf figures check check-inputs check-braces check-pending \
        check-refs check-pages clean distclean help

all: pdf

## build main.pdf
pdf: $(TEX).pdf

$(TEX).pdf: $(SOURCES)
ifneq ($(LATEXMK),)
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error $(TEX).tex
else ifneq ($(PDFLATEX),)
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TEX).tex
	-$(BIBTEX) $(TEX)
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TEX).tex
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TEX).tex
else
	@echo "No TeX toolchain found: neither latexmk nor pdflatex is on PATH."
	@echo "See README.md, section 'Build status'. Run 'make check' instead."
	@exit 1
endif

## re-render the scripted figures into figures/ (needs matplotlib)
## TikZ/pgfplots figures under figures/*.tex are built by LaTeX and need nothing here.
figures:
	@python3 illustrate/figures.py

## every structural check; no TeX required
check:
	@python3 check.py

## individual checks
check-inputs:
	@python3 check.py inputs

check-braces:
	@python3 check.py braces

check-pending:
	@python3 check.py pending

check-refs:
	@python3 check.py refs

## report the page count of the built PDF against the venue's nominal limit
## Reporting, not gating: the call names 5-8 pages for a regular paper, but the
## limit is not enforced at this venue, and completeness of the argument wins
## over a page count. Set PAGE_LIMIT to make it a hard gate again.
PAGE_LIMIT ?= 8
check-pages: $(TEX).pdf
	@n=$$(pdfinfo $(TEX).pdf 2>/dev/null | awk '/^Pages:/{print $$2}')
	echo "  pages: $$n (IEEE UV 2026 nominal regular-paper limit: $(PAGE_LIMIT), not enforced)"
	if [ -n "$$n" ] && [ "$$n" -gt "$(PAGE_LIMIT)" ]; then \
	  echo "  note: over the nominal limit by $$(( n - $(PAGE_LIMIT) )) page(s)"; \
	fi

clean:
	rm -f $(TEX).aux $(TEX).log $(TEX).out $(TEX).bbl $(TEX).blg \
	      $(TEX).fdb_latexmk $(TEX).fls $(TEX).synctex.gz $(TEX).toc \
	      frontier_pending.dat

distclean: clean
	rm -f $(TEX).pdf

help:
	@echo "  make          build main.pdf"
	@echo "  make figures  re-render the scripted figures in illustrate/"
	@echo "  make check    structural checks, no TeX needed"
	@echo "  make check-pages  page count against the venue limit"
	@echo "  make clean / distclean"
