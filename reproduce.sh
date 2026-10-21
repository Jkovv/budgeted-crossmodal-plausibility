#!/usr/bin/env bash
# Same steps as `make all`, for machines without make (on Windows, run it from
# Git Bash or WSL).
#
#   ./reproduce.sh            full run, writes results/ and re-executes the notebook
#   ./reproduce.sh --quick    same as `make all-quick`, writes results-quick/
#
# PYTHON and WORKERS can be set as for make, e.g. WORKERS=6 ./reproduce.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python}
WORKERS=${WORKERS:-3}
export PYTHONPATH=src

case "${1:-}" in
    "")      notebook=(--inplace) ;;
    --quick) export BCP_QUICK=1
             notebook=(--output-dir results-quick --output walkthrough) ;;
    *)       echo "usage: $0 [--quick]" >&2; exit 2 ;;
esac

run() {
    echo ">> $*"
    "$@"
}

run "$PYTHON" data/download_mimic_demo.py
run "$PYTHON" -m bcp.cli prepare
for step in primary ablation sensitivity; do
    run "$PYTHON" -m bcp.cli "$step" --workers "$WORKERS"
done
for step in evaluate figures explain; do
    run "$PYTHON" -m bcp.cli "$step"
done
run "$PYTHON" -m jupyter nbconvert --to notebook --execute "${notebook[@]}" notebooks/walkthrough.ipynb
echo "done"
