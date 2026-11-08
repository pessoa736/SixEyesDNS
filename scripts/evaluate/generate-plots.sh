#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RESULTS_DIR="${RESULTS_DIR:-results/autoencoder}"
PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ "$PYTHON_BIN" == "python" && -x "$ROOT_DIR/.venv-amd/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv-amd/bin/python"
fi

if [[ ! -f "$RESULTS_DIR/history.json" ||
      ! -f "$RESULTS_DIR/metrics.json" ]]; then
    echo "Erro: resultados de treinamento não encontrados em: $RESULTS_DIR" >&2
    echo "Execute um script em ./scripts/model/ antes da plotagem." >&2
    exit 1
fi

echo "Gerando gráficos do modelo em: $RESULTS_DIR"

"$PYTHON_BIN" -m source.plot_training \
    --results-dir "$RESULTS_DIR" \
    "$@"
