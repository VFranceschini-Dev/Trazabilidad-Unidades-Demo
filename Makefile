SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: demo up down reset seed migrar actas gps test capturas paquete logs nginx-cert

## demo: todo desde cero (.env + certificado + build + up + migrar + seed + actas)
demo: nginx-cert
	@[ -f .env ] || (echo "== copiando .env desde .env.example =="; cp .env.example .env)
	$(COMPOSE) up -d --build
	$(MAKE) migrar
	$(MAKE) seed
	$(MAKE) actas || true
	@echo "== demo lista: https://localhost · https://localhost/api/v1/docs · http://localhost:5678 (n8n) =="

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

## reset: BORRA volumenes (pide confirmacion)
reset:
	@read -p "¿Borrar TODOS los volumenes (base de datos, n8n, Traccar)? [y/N] " r; \
	  if [ "$$r" = "y" ]; then $(COMPOSE) down -v; else echo "cancelado"; fi

nginx-cert:
	bash nginx/generar_certificado.sh

migrar:
	$(COMPOSE) exec -T api alembic upgrade head

seed:
	$(COMPOSE) exec -T api python /srv/scripts/seed.py

## actas: genera y envia actas de prueba al buzon de n8n (se completa en etapa 2)
actas:
	$(COMPOSE) exec -T api python /srv/scripts/generar_actas.py
	$(COMPOSE) exec -T api python /srv/scripts/enviar_actas.py

gps:
	$(COMPOSE) exec -T api python /srv/scripts/simular_gps.py

## test: suite completa en contenedor (perfil "test": imagen con requirements-dev.txt, tests/ montado)
## si Docker no esta disponible, cae a pytest local (mismas dependencias de requirements-dev.txt)
test:
	@if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then \
		docker compose build test && docker compose run --rm test; \
	else \
		echo "== Docker no disponible: ejecutando pytest local =="; \
		python -m pytest tests -q --maxfail=999; \
	fi

## lint: ruff + mypy (en el contenedor de test cuando hay Docker)
lint:
	$(COMPOSE) run --rm test bash -c "cd /srv/backend && ruff check . ../tests && mypy app/core"

capturas:
	python scripts/capturas.py

paquete:
	python scripts/empaquetar.py

logs:
	$(COMPOSE) logs -f --tail=100
