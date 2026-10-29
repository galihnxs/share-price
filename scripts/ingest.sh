#!/usr/bin/env bash
# Module 3: embed new filings + notes into ChromaDB, then run two smoke-test queries.
# Log: data/ingest_log.txt
set -euo pipefail
cd "$(dirname "$0")/.."
exec > >(tee data/ingest_log.txt) 2>&1
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate shareprice
time python main.py --ingest --notes
python main.py --query "debt maturities and refinancing risk" --ticker ZIM -k 3
python main.py --query "customer concentration or contract termination" -k 4
echo ">> INGEST OK"
