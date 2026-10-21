# Reproduce everything from scratch:  make all
# Short run with 2 replicates (1 for ablation and sensitivity) and a smaller
# bootstrap, written to results-quick/:  make all-quick
# Set BCP_DATA_DIR to keep the raw demo files outside the repository.
PYTHON ?= python
# parallel replicates; empty means cores / 4, since every model fit uses 4 threads
WORKERS ?=
export PYTHONPATH := src

.PHONY: all all-quick install data prepare primary ablation sensitivity evaluate figures explain notebook notebook-quick test clean

all: data prepare primary ablation sensitivity evaluate figures explain notebook

all-quick:
	BCP_QUICK=1 $(MAKE) data prepare primary ablation sensitivity evaluate figures explain notebook-quick

install:
	$(PYTHON) -m pip install -r requirements.txt

data:
	$(PYTHON) data/download_mimic_demo.py

prepare:
	$(PYTHON) -m bcp.cli prepare

primary:
	$(PYTHON) -m bcp.cli primary $(if $(WORKERS),--workers $(WORKERS))

ablation:
	$(PYTHON) -m bcp.cli ablation $(if $(WORKERS),--workers $(WORKERS))

sensitivity:
	$(PYTHON) -m bcp.cli sensitivity $(if $(WORKERS),--workers $(WORKERS))

evaluate:
	$(PYTHON) -m bcp.cli evaluate

figures:
	$(PYTHON) -m bcp.cli figures

explain:
	$(PYTHON) -m bcp.cli explain

notebook:
	$(PYTHON) -m jupyter nbconvert --to notebook --execute --inplace notebooks/walkthrough.ipynb

# the executed copy goes next to the quick results, the committed notebook is left alone
notebook-quick:
	BCP_QUICK=1 $(PYTHON) -m jupyter nbconvert --to notebook --execute notebooks/walkthrough.ipynb --output-dir results-quick --output walkthrough

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf data/processed results/cells results/tables/*.csv results/tables/*.json results/figures/*.png results/summary.json results-quick
