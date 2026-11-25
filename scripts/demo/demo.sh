#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
MODEL_DIR="${MODEL_DIR:-results/autoencoder-hybrid}"
REPLAY_LOG="${REPLAY_LOG:-scripts/demo/replay-example.txt}"
if [[ "$PYTHON_BIN" == "python" && -x "$ROOT_DIR/.venv-amd/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv-amd/bin/python"
fi

if [[ ! -f "$MODEL_DIR/model.pt" ]]; then
    echo "Erro: checkpoint não encontrado em $MODEL_DIR/model.pt" >&2
    echo "Treine o modelo ou informe MODEL_DIR antes de executar a demo." >&2
    exit 1
fi
if [[ ! -f "$REPLAY_LOG" ]]; then
    echo "Erro: log de replay não encontrado em $REPLAY_LOG" >&2
    echo "Informe REPLAY_LOG ou passe --replay <arquivo>." >&2
    exit 1
fi

DEMO_ARGS=(--model-dir "$MODEL_DIR" --replay "$REPLAY_LOG")
if [[ -n "${LIMIT:-}" ]]; then
    DEMO_ARGS+=(--limit "$LIMIT")
fi

exec "$PYTHON_BIN" -m source.demo "${DEMO_ARGS[@]}" "$@"
