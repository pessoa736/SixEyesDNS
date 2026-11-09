#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
SPLITS_DIR="${SPLITS_DIR:-data/processed/splits}"
OUTPUT_DIR="${OUTPUT_DIR:-results/evaluation}"
if [[ "$PYTHON_BIN" == "python" && -x "$ROOT_DIR/.venv-amd/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv-amd/bin/python"
fi

for mode in semantic lexical hybrid; do
    if [[ ! -f "results/autoencoder-$mode/model.pt" ]]; then
        echo "Erro: checkpoint não encontrado em results/autoencoder-$mode/model.pt" >&2
        echo "Treine com ./scripts/model/train-$mode.sh antes de avaliar." >&2
        exit 1
    fi
done

exec "$PYTHON_BIN" -m source.evaluate \
    --splits-dir "$SPLITS_DIR" \
    --output-dir "$OUTPUT_DIR" \
    "$@"
