PYTHON ?= python

# Every target delegates to run.py, which works on Windows, macOS and Linux without make.
.PHONY: data model report facts app test check regression all

data:
	$(PYTHON) run.py data

model:
	$(PYTHON) run.py model

report:
	$(PYTHON) run.py report

facts:
	$(PYTHON) run.py facts

app:
	$(PYTHON) run.py

test:
	$(PYTHON) run.py test

check:
	$(PYTHON) run.py check

regression:
	$(PYTHON) run.py regression

all:
	$(PYTHON) run.py all
