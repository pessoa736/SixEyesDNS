#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

./scripts/model/train-lexical.sh "$@"
./scripts/model/train-semantic.sh "$@"
OUTPUT_DIR="${HYBRID_OUTPUT_DIR:-results/autoencoder-hybrid}"
OUTPUT_DIR="$OUTPUT_DIR" \
    LEXICAL_CHECKPOINT=results/autoencoder-lexical/model.pt \
    ./scripts/model/train-hybrid.sh "$@"
