"""Envio de correo por SMTP. En la demo llega a GreenMail, nunca a una casilla real."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate

from app.core import logs
from app.core.config import settings


def enviar(destino: str, asunto: str, cuerpo: str) -> bool:
    """Una falla de correo no rompe la operacion: se registra sin el contenido, que lleva secretos."""
    mensaje = EmailMessage()
    mensaje["From"] = settings.correo_remitente
    mensaje["To"] = destino
    mensaje["Subject"] = asunto
    mensaje["Date"] = formatdate(localtime=True)
    mensaje.set_content(cuerpo)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.send_message(mensaje)
    except (OSError, smtplib.SMTPException) as exc:
        logs.log_evento("correo.envio", estado="fracaso", motivo=type(exc).__name__)
        return False
    logs.log_evento("correo.envio", estado="exito")
    return True
