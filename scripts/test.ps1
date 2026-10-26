# Ejecuta la suite de pruebas dentro de Docker (perfil "test") contra una base
# PostgreSQL efimera del servicio db. Equivalente a `make test`.
$ErrorActionPreference = "Stop"
Set-Location -Path (Join-Path $PSScriptRoot "..")
docker compose --profile test run --rm test
exit $LASTEXITCODE
