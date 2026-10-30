#!/usr/bin/env bash
# Genera el certificado autofirmado para https://localhost (se monta en ./certs/).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$DIR/certs/server.crt" ]; then
  echo "== certificado existente, no se regenera =="
  exit 0
fi
mkdir -p "$DIR/certs"
cd "$DIR"
# Git Bash en Windows convierte -subj "/C=..." en una ruta si no se desactiva la conversion;
# por eso las rutas de openssl son relativas a esta carpeta.
export MSYS_NO_PATHCONV=1
openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout certs/server.key -out certs/server.crt \
  -subj "/C=AR/O=Demo Unidades Demo/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 certs/server.key
echo "== certificado autofirmado generado en nginx/certs/ =="
