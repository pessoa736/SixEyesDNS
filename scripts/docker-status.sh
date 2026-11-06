#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Containers do SixEyesDNS:"
docker compose ps

echo
echo "Todos os containers em execução:"
docker ps
