#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LABELS_PATH="${2:-data/raw/query_labels.csv}"
OUTPUT_PATH="${3:-data/processed/dataset.csv}"
SPLITS_DIR="${4:-data/processed/splits}"
SEED="${SEED:-42}"
PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ "$PYTHON_BIN" == "python" && -x "$ROOT_DIR/.venv-amd/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv-amd/bin/python"
fi

if [[ -n "${1:-}" ]]; then
    LOG_PATHS=("$1")
else
    LOG_PATHS=()
    for candidate in data/raw/dnsmasq/dnsmasq.log data/raw/bind9/queries.log; do
        if [[ -f "$candidate" ]]; then
            LOG_PATHS+=("$candidate")
        fi
    done
fi

if [[ ${#LOG_PATHS[@]} -eq 0 ]]; then
    echo "Erro: nenhum log DNS encontrado em data/raw/{dnsmasq,bind9}" >&2
    exit 1
fi

for log_path in "${LOG_PATHS[@]}"; do
    if [[ ! -f "$log_path" ]]; then
        echo "Erro: log DNS não encontrado: $log_path" >&2
        exit 1
    fi
done

if [[ ! -f "$LABELS_PATH" ]]; then
    echo "Erro: arquivo de rótulos não encontrado: $LABELS_PATH" >&2
    exit 1
fi

echo "Logs DNS utilizados: ${LOG_PATHS[*]}"
"$PYTHON_BIN" source/process_raw.py \
    --log "${LOG_PATHS[@]}" \
    --labels "$LABELS_PATH" \
    --output "$OUTPUT_PATH"

"$PYTHON_BIN" source/split_dataset.py \
    --input "$OUTPUT_PATH" \
    --output-dir "$SPLITS_DIR" \
    --seed "$SEED"

echo "Dados processados e separados em $SPLITS_DIR."
