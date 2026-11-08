#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

SPLITS_DIR="${SPLITS_DIR:-data/processed/splits}"
OUTPUT_DIR="${OUTPUT_DIR:-results/autoencoder}"
PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ "$PYTHON_BIN" == "python" && -x "$ROOT_DIR/.venv-amd/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv-amd/bin/python"
fi

if [[ ! -f "$SPLITS_DIR/train.csv" ||
      ! -f "$SPLITS_DIR/validation.csv" ||
      ! -f "$SPLITS_DIR/test.csv" ]]; then
    echo "Erro: splits não encontrados em: $SPLITS_DIR" >&2
    echo "Execute ./scripts/data/process-data.sh antes do treinamento." >&2
    exit 1
fi

echo "Iniciando treinamento do autoencoder."
echo "Splits: $SPLITS_DIR"
echo "Saída: $OUTPUT_DIR"

"$PYTHON_BIN" -m source.train \
    --mode hybrid \
    --splits-dir "$SPLITS_DIR" \
    --output-dir "$OUTPUT_DIR" \
    "$@"

echo "Modelo salvo em: $OUTPUT_DIR/model.pt"
echo "Histórico salvo em: $OUTPUT_DIR/history.json"
echo "Métricas salvas em: $OUTPUT_DIR/metrics.json"
