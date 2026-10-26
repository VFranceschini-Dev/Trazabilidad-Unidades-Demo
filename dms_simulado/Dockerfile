FROM python:3.12-slim
WORKDIR /srv
# Contexto de build = raiz del repo (ver docker-compose.yml)
COPY dms_simulado/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY dms_simulado/ /srv/
EXPOSE 8100
CMD ["uvicorn", "dms_app:app", "--host", "0.0.0.0", "--port", "8100"]
