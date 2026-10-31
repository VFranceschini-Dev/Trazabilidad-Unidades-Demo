FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# poppler para la vista previa y las actas de prueba; el OCR corre en n8n
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*

# Contexto de build = raiz del repo (ver docker-compose.yml): se copian backend/, scripts/ y datos_demo/
# Carpeta de actas compartida con n8n (usuario 1000), que guarda los PDF
RUN mkdir -p /actas && chown 1000:1000 /actas

COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

COPY backend/ /srv/backend/
COPY scripts/ /srv/scripts/
COPY datos_demo/ /srv/datos_demo/

WORKDIR /srv/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
