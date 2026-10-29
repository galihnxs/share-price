#!/usr/bin/env bash
# One-time setup: creates conda env "shareprice" (Python 3.14), installs requirements,
# checks Apple Silicon GPU (MPS), downloads + tests the embedding model, runs tests.
# Leaves the ind5003 course env untouched. Log: data/setup_log.txt
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
exec > >(tee data/setup_log.txt) 2>&1

CONDA_BASE="$(conda info --base 2>/dev/null || echo /opt/homebrew/Caskroom/miniforge/base)"
source "$CONDA_BASE/etc/profile.d/conda.sh"

if conda env list | grep -qE '^shareprice\s'; then
  echo ">> env shareprice exists, reusing"
else
  echo ">> creating env shareprice (python 3.14)"
  conda create -y -n shareprice -c conda-forge python=3.14
fi
conda activate shareprice
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo ">> verifying"
python - <<'PY'
import sys, platform, importlib
print("python", sys.version.split()[0], platform.machine())
for m in ["pandas","numpy","sklearn","xgboost","lightgbm","torch","sentence_transformers","chromadb","pypdf"]:
    print(f"  {m:22s}", importlib.import_module(m).__version__)
import torch
print("MPS available:", torch.backends.mps.is_available())
from sentence_transformers import SentenceTransformer
dev = "mps" if torch.backends.mps.is_available() else "cpu"
m = SentenceTransformer("BAAI/bge-small-en-v1.5", device=dev)
v = m.encode(["maturing debt wall in 2027", "refinancing risk on senior notes"], normalize_embeddings=True)
print(f"embedding ok on {dev}: dim={v.shape[1]} cosine={float(v[0]@v[1]):.3f}")
PY
python -m pytest -q tests
echo ">> SETUP OK"
