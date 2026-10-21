# Reproduce everything from scratch:  make all
# Set BCP_DATA_DIR to keep the raw demo files outside the repository.
PYTHON ?= python
export PYTHONPATH := src

.PHONY: all install data test clean

all: data

install:
	$(PYTHON) -m pip install -r requirements.txt

data:
	$(PYTHON) data/download_mimic_demo.py

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf data/processed results/cells
