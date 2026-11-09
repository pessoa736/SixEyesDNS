#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data/raw/dnsmasq data/raw/bind9 data/raw/resolver data/raw/dhcp

COMPOSE_CONFIG="$(docker compose config)"
echo "Parâmetros efetivos do gerador (defina QUERY_COUNT, ANOMALY_RATE e SEED no ambiente para alterá-los):"
for variable in QUERY_COUNT ANOMALY_RATE SEED; do
    value="$(awk -v key="$variable" '$1 == key ":" { gsub(/"/, "", $2); print $2; exit }' <<< "$COMPOSE_CONFIG")"
    echo "  $variable=$value"
done

echo
echo "Iniciando servidores DNS, DHCP e o gerador..."
docker compose up --build --force-recreate -d

echo
docker compose ps
