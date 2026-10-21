# Reproduce everything from scratch:  make all
# Set BCP_DATA_DIR to keep the raw demo files outside the repository.
PYTHON ?= python
WORKERS ?= 3
export PYTHONPATH := src

.PHONY: all install data prepare primary ablation sensitivity evaluate figures notebook test clean

all: data prepare primary ablation sensitivity evaluate figures

install:
	$(PYTHON) -m pip install -r requirements.txt

data:
	$(PYTHON) data/download_mimic_demo.py

prepare:
	$(PYTHON) -m bcp.cli prepare

primary:
	$(PYTHON) -m bcp.cli primary --workers $(WORKERS)

ablation:
	$(PYTHON) -m bcp.cli ablation --workers $(WORKERS)

sensitivity:
	$(PYTHON) -m bcp.cli sensitivity --workers $(WORKERS)

evaluate:
	$(PYTHON) -m bcp.cli evaluate

figures:
	$(PYTHON) -m bcp.cli figures

notebook:
	$(PYTHON) -m jupyter nbconvert --to notebook --execute --inplace notebooks/walkthrough.ipynb

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf data/processed results/cells results/tables/*.csv results/tables/*.json results/figures/*.png results/summary.json
