#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
OUTPUT_DIR="${OUTPUT_DIR:-results/autoencoder-semantic}"
PLOT_AFTER_TRAINING="${PLOT_AFTER_TRAINING:-1}"

"$PYTHON_BIN" -m source.train \
    --mode semantic \
    --output-dir "$OUTPUT_DIR" \
    "$@"

if [[ "$PLOT_AFTER_TRAINING" == "1" ]]; then
    "$PYTHON_BIN" -m source.plot_training \
        --results-dir "$OUTPUT_DIR" \
        --test-samples "${TEST_SAMPLES:-12}"
fi
