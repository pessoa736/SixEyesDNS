#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
RESULTS_DIR="${RESULTS_DIR:-results/autoencoder-lexical}"
SPLITS_DIR="${SPLITS_DIR:-data/processed/splits}"
SAMPLES="${SAMPLES:-12}"

if [[ ! -f "$RESULTS_DIR/model.pt" ]]; then
    echo "Erro: checkpoint não encontrado em $RESULTS_DIR/model.pt" >&2
    echo "Treine um modelo antes de executar este teste." >&2
    exit 1
fi

exec "$PYTHON_BIN" -m source.test_model \
    --results-dir "$RESULTS_DIR" \
    --splits-dir "$SPLITS_DIR" \
    --samples "$SAMPLES"
