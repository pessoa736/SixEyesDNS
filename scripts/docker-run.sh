#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data/raw/dnsmasq

echo "Iniciando dnsmasq e o gerador..."
docker compose up --build -d

echo
docker compose ps
