#!/usr/bin/env bash
# Genera el certificado autofirmado para https://localhost (se monta en ./certs/).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$DIR/certs/server.crt" ]; then
  echo "== certificado existente, no se regenera =="
  exit 0
fi
mkdir -p "$DIR/certs"
openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout "$DIR/certs/server.key" -out "$DIR/certs/server.crt" \
  -subj "/C=AR/O=Demo Unidades Demo/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 "$DIR/certs/server.key"
echo "== certificado autofirmado generado en nginx/certs/ =="
