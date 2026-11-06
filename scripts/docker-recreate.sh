#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data/raw/dnsmasq

echo "Parando e removendo containers, volumes nomeados e redes deste projeto..."
docker compose down --volumes --remove-orphans

echo "Reconstruindo imagens sem cache..."
docker compose build --no-cache

echo "Criando containers e rede novamente..."
docker compose up -d --force-recreate

echo
docker compose ps
