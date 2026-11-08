#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data/raw/dnsmasq data/raw/bind9 data/raw/resolver data/raw/dhcp

echo "Iniciando servidores DNS, DHCP e o gerador..."
docker compose up --build --force-recreate -d

echo
docker compose ps
