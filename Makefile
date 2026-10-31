SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: demo up down reset seed migrar actas gps test capturas paquete logs nginx-cert

## demo: todo desde cero (.env + certificado + build + up + migrar + seed + actas)
demo: nginx-cert
	@[ -f .env ] || (echo "== copiando .env desde .env.example =="; cp .env.example .env)
	$(COMPOSE) up -d --build
	$(MAKE) migrar
	$(MAKE) seed
	$(MAKE) gps
	$(MAKE) actas
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

## Objetivos de etapas siguientes: avisan y terminan bien mientras no exista su script
actas:
	@if [ -f scripts/generar_actas.py ]; then \
	  $(COMPOSE) exec -T api python /srv/scripts/generar_actas.py && \
	  $(COMPOSE) exec -T api python /srv/scripts/enviar_actas.py; \
	else echo "== actas: se agrega en la etapa de infracciones =="; fi

gps:
	$(COMPOSE) exec -T api python /srv/scripts/simular_gps.py

## test: suite completa dentro de Docker (perfil test) contra Postgres efimero del servicio db
test:
	$(COMPOSE) --profile test run --rm test

capturas:
	@if [ -f scripts/capturas.py ]; then python scripts/capturas.py; \
	else echo "== capturas: se agrega en la etapa de empaquetado =="; fi

paquete:
	@if [ -f scripts/empaquetar.py ]; then python scripts/empaquetar.py; \
	else echo "== paquete: se agrega en la etapa de empaquetado =="; fi

logs:
	$(COMPOSE) logs -f --tail=100
