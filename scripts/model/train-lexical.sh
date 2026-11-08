#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
OUTPUT_DIR="${OUTPUT_DIR:-results/autoencoder-lexical}"

exec "$PYTHON_BIN" -m source.train \
    --mode lexical \
    --fresh \
    --output-dir "$OUTPUT_DIR" \
    "$@"
