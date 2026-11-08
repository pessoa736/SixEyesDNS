#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

./scripts/model/train-lexical.sh "$@"
./scripts/model/train-semantic.sh "$@"
OUTPUT_DIR="${HYBRID_OUTPUT_DIR:-results/autoencoder-hybrid}"
PYTHON_BIN="${PYTHON_BIN:-python}"
exec "$PYTHON_BIN" -m source.train \
    --mode hybrid \
    --fresh \
    --lexical-checkpoint results/autoencoder-lexical/model.pt \
    --output-dir "$OUTPUT_DIR" \
    "$@"
