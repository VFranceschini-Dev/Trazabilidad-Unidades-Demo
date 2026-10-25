FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# Contexto de build = raiz del repo (ver docker-compose.yml): se copian backend/, scripts/ y datos_demo/
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

COPY backend/ /srv/backend/
COPY scripts/ /srv/scripts/
COPY datos_demo/ /srv/datos_demo/

WORKDIR /srv/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
