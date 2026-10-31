"""Muestra los ultimos correos de una casilla de GreenMail. Solo con ENTORNO=demo: contienen enlaces y claves.

Uso: python /srv/scripts/ver_correo.py mkt@demo.local
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import os
import sys

SERVIDOR = os.environ.get("SMTP_HOST", "mail")
PUERTO_IMAP = int(os.environ.get("IMAP_PORT", "3143"))
CANTIDAD = 5


def principal(casilla: str) -> None:
    if os.environ.get("ENTORNO") != "demo":
        sys.exit("== solo disponible con ENTORNO=demo ==")
    with imaplib.IMAP4(SERVIDOR, PUERTO_IMAP, timeout=20) as imap:
        # GreenMail crea la casilla al recibir el primer correo, con la direccion como clave
        try:
            imap.login(casilla, casilla)
        except imaplib.IMAP4.error:
            sys.exit(f"== {casilla} todavia no recibio correos ==")
        imap.select("INBOX", readonly=True)
        _, datos = imap.search(None, "ALL")
        ids = datos[0].split()
        if not ids:
            print(f"== {casilla} no tiene correos ==")
        for num in ids[-CANTIDAD:]:
            _, partes = imap.fetch(num, "(RFC822)")
            mensaje = email.message_from_bytes(partes[0][1], policy=email.policy.default)
            print(f"\n--- {mensaje['Date']} · {mensaje['Subject']}")
            print(mensaje.get_content().strip())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python /srv/scripts/ver_correo.py <correo>")
    principal(sys.argv[1])
