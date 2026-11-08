#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

SPLITS_DIR="${SPLITS_DIR:-data/processed/splits}"
OUTPUT_DIR="${OUTPUT_DIR:-results/autoencoder}"
PYTHON_BIN="${PYTHON_BIN:-python}"
PLOT_AFTER_TRAINING="${PLOT_AFTER_TRAINING:-1}"
LEXICAL_CHECKPOINT="${LEXICAL_CHECKPOINT:-results/autoencoder-lexical/model.pt}"
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

TRAIN_ARGS=(
    --mode hybrid
    --splits-dir "$SPLITS_DIR"
    --output-dir "$OUTPUT_DIR"
)
if [[ -f "$LEXICAL_CHECKPOINT" ]]; then
    TRAIN_ARGS+=(--lexical-checkpoint "$LEXICAL_CHECKPOINT")
fi

"$PYTHON_BIN" -m source.train "${TRAIN_ARGS[@]}" "$@"

if [[ "$PLOT_AFTER_TRAINING" == "1" ]]; then
    "$PYTHON_BIN" -m source.plot_training \
        --results-dir "$OUTPUT_DIR" \
        --test-samples "${TEST_SAMPLES:-12}"
fi

echo "Modelo salvo em: $OUTPUT_DIR/model.pt"
echo "Histórico salvo em: $OUTPUT_DIR/history.json"
echo "Métricas salvas em: $OUTPUT_DIR/metrics.json"
