#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_PATH="${1:-data/raw/dnsmasq/dnsmasq.log}"
LABELS_PATH="${2:-data/raw/query_labels.csv}"
OUTPUT_PATH="${3:-data/processed/dataset.csv}"
SPLITS_DIR="${4:-data/processed/splits}"
SEED="${SEED:-42}"

if [[ ! -f "$LOG_PATH" ]]; then
    echo "Erro: log DNS não encontrado: $LOG_PATH" >&2
    exit 1
fi

if [[ ! -f "$LABELS_PATH" ]]; then
    echo "Erro: arquivo de rótulos não encontrado: $LABELS_PATH" >&2
    exit 1
fi

python source/process_raw.py \
    --log "$LOG_PATH" \
    --labels "$LABELS_PATH" \
    --output "$OUTPUT_PATH"

python source/split_dataset.py \
    --input "$OUTPUT_PATH" \
    --output-dir "$SPLITS_DIR" \
    --seed "$SEED"

echo "Dados processados e separados em $SPLITS_DIR."
