"""Envia las actas de prueba por correo a la casilla que lee n8n (GreenMail, sin correo real)."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

CARPETA = Path(__file__).resolve().parent.parent / "datos_demo" / "actas_prueba"
SERVIDOR = os.environ.get("SMTP_HOST", "mail")
PUERTO = int(os.environ.get("SMTP_PORT", "3025"))
DESTINO = "administracion@demo.local"


def enviar() -> int:
    actas = sorted(CARPETA.glob("*.pdf"))
    if not actas:
        raise SystemExit("No hay actas: corra primero scripts/generar_actas.py.")
    with smtplib.SMTP(SERVIDOR, PUERTO, timeout=20) as smtp:
        for ruta in actas:
            mensaje = EmailMessage()
            mensaje["From"] = "notificaciones@transito.demo.local"
            mensaje["To"] = DESTINO
            mensaje["Subject"] = f"Acta de infracción {ruta.stem}"
            mensaje.set_content("Se adjunta el acta de infracción. Datos ficticios de demostración.")
            mensaje.add_attachment(ruta.read_bytes(), maintype="application", subtype="pdf", filename=ruta.name)
            smtp.send_message(mensaje)
            print(f"== enviada {ruta.name}")
    return len(actas)


if __name__ == "__main__":
    enviar()
