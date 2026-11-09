#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
RESULTS_DIR="${RESULTS_DIR:-results/autoencoder-lexical}"
SPLITS_DIR="${SPLITS_DIR:-data/processed/splits}"
TEST_SAMPLES="${TEST_SAMPLES:-12}"

exec "$PYTHON_BIN" -m source.plot_training \
    --results-dir "$RESULTS_DIR" \
    --splits-dir "$SPLITS_DIR" \
    --test-samples "$TEST_SAMPLES" \
    "$@"
