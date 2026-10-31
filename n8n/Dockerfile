FROM n8nio/n8n:1.53.2

# n8n procesa las actas (TFG): Tesseract en espanol, poppler para rasterizar y Python para el lector
USER root
RUN apk add --no-cache tesseract-ocr tesseract-ocr-data-spa poppler-utils python3 \
    && python3 -m venv /opt/ocr \
    && /opt/ocr/bin/pip install --no-cache-dir pdfplumber==0.11.4 pdf2image==1.17.0 pytesseract==0.3.13 \
    && mkdir -p /actas && chown node:node /actas
USER node
