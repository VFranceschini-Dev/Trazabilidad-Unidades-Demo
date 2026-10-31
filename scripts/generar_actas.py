"""Genera las 8 actas de prueba siguiendo el modelo de ref_modelo_acta.jpg (datos ficticios).

Cinco con texto nitido (una repite un numero), dos rasterizadas con ruido y rotacion leve y
una ilegible. La primera corresponde a la patente y al horario de un test drive de la semilla.
"""

from __future__ import annotations

import io
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from pdf2image import convert_from_bytes  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

AR = ZoneInfo("America/Argentina/Buenos_Aires")
SALIDA = Path(__file__).resolve().parent.parent / "datos_demo" / "actas_prueba"


@dataclass(frozen=True)
class DatosActa:
    nro_acta: str
    patente: str
    momento: datetime
    jurisdiccion: str
    lugar: str
    monto: str = "185.400,00"
    vencimiento: datetime | None = None


def _pesos(monto: str) -> str:
    return f"$ {monto}"


def pdf_nitido(d: DatosActa) -> bytes:
    """Acta con capa de texto, con la disposicion del modelo generico."""
    vencimiento = d.vencimiento or datetime.now(AR) + timedelta(days=30)
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=A4)
    ancho, alto = A4
    c.setFillColorRGB(0.35, 0.39, 0.46)
    c.rect(0, alto - 40, ancho, 40, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(ancho / 2, alto - 26, "ACTA DE PRUEBA - USO ACADEMICO - DATOS FICTICIOS, SIN VALIDEZ LEGAL")
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, alto - 80, f"Organismo de Transito - {d.jurisdiccion}")
    c.setFont("Helvetica", 11)
    y = alto - 120
    for linea in (
        f"Acta N: {d.nro_acta}",
        f"Fecha de emision: {d.momento + timedelta(days=2):%d/%m/%Y}",
        "",
        "Datos del vehiculo",
        f"Dominio: {d.patente}",
        "Marca / Modelo: Ford",
        "",
        "Infraccion constatada",
        "Descripcion: Exceder el limite de velocidad establecido",
        f"Fecha: {d.momento:%d/%m/%Y} Hora: {d.momento:%H:%M}",
        f"Lugar: {d.lugar}",
        f"Jurisdiccion: {d.jurisdiccion}",
        "",
        "Liquidacion",
        f"Importe de la multa: {_pesos(d.monto)}",
        f"Fecha de vencimiento: {vencimiento:%d/%m/%Y}",
    ):
        c.drawString(40, y, linea)
        y -= 22
    c.save()
    return salida.getvalue()


def pdf_rasterizado(d: DatosActa, semilla: int) -> bytes:
    """Sin capa de texto, con ruido y rotacion leve, como un escaneo."""
    azar = random.Random(semilla)
    imagen = convert_from_bytes(pdf_nitido(d), dpi=200)[0].convert("L").rotate(azar.uniform(-0.8, 0.8), fillcolor=255)
    pixeles = imagen.load()
    for _ in range(imagen.width * imagen.height // 400):
        pixeles[azar.randrange(imagen.width), azar.randrange(imagen.height)] = azar.randint(90, 200)
    salida = io.BytesIO()
    imagen.convert("RGB").save(salida, format="PDF", resolution=200)
    return salida.getvalue()


def pdf_ilegible() -> bytes:
    salida = io.BytesIO()
    Image.effect_noise((800, 1100), 90).convert("RGB").filter(ImageFilter.GaussianBlur(3)).save(salida, format="PDF")
    return salida.getvalue()


def test_drive_del_guion() -> tuple[str, datetime]:
    """Patente y un instante dentro del ultimo test drive cerrado de la semilla."""
    from sqlalchemy import select

    from app.comercial.models import UsoComercial
    from app.core.db import SessionLocal
    from app.unidades.models import UnidadDemo

    with SessionLocal() as sesion:
        fila = sesion.execute(
            select(UnidadDemo.patente, UsoComercial.fecha_hora_salida, UsoComercial.fecha_hora_regreso)
            .join(UsoComercial, UsoComercial.id_unidad == UnidadDemo.id)
            .where(UsoComercial.tipo_uso == "TEST_DRIVE", UsoComercial.fecha_hora_regreso.is_not(None))
            .order_by(UsoComercial.fecha_hora_salida.desc())
            .limit(1)
        ).first()
    if fila is None:
        raise SystemExit("No hay test drives: corra primero la semilla.")
    patente, salida, regreso = fila
    return patente, (salida + (regreso - salida) / 2).astimezone(AR).replace(second=0, microsecond=0)


def generar() -> list[Path]:
    SALIDA.mkdir(parents=True, exist_ok=True)
    patente, momento = test_drive_del_guion()
    hoy = datetime.now(timezone.utc).astimezone(AR).replace(second=0, microsecond=0)
    guion = DatosActa("2026-110001", patente, momento, "Municipalidad de Resistencia", "Av. Sarmiento 1200, Resistencia")
    actas: dict[str, bytes] = {
        "01_guion_test_drive.pdf": pdf_nitido(guion),
        "02_corrientes.pdf": pdf_nitido(DatosActa("2026-110002", "AK011LM", hoy - timedelta(days=12), "Municipalidad de Corrientes", "Av. 3 de Abril 900, Corrientes", "98.750,00")),
        "03_formosa.pdf": pdf_nitido(DatosActa("2026-110003", "AG007HI", hoy - timedelta(days=22, hours=2), "Municipalidad de Formosa", "Av. 25 de Mayo 450, Formosa", "142.300,00")),
        "04_saenz_pena_patente_ajena.pdf": pdf_nitido(DatosActa("2026-110004", "ZZ 999 ZZ", hoy - timedelta(days=4), "Municipalidad de Saenz Pena", "Calle 12 N 300, Saenz Pena", "76.000,00")),
        "05_numero_repetido.pdf": pdf_nitido(guion),
        "06_ruta_11_escaneada.pdf": pdf_rasterizado(DatosActa("2026-110006", "AE 005 FG", hoy - timedelta(days=5, hours=2), "Vialidad Nacional", "Ruta Nacional 11 km 1003", "210.500,00"), 6),
        "07_resistencia_escaneada.pdf": pdf_rasterizado(DatosActa("2026-110007", "AH 008 IJ", hoy - timedelta(days=7, hours=2), "Municipalidad de Resistencia", "Av. Alberdi 300, Resistencia", "88.900,00"), 7),
        "08_ilegible.pdf": pdf_ilegible(),
    }
    rutas = []
    for nombre, contenido in actas.items():
        ruta = SALIDA / nombre
        ruta.write_bytes(contenido)
        rutas.append(ruta)
    return rutas


if __name__ == "__main__":
    for ruta in generar():
        print(f"== generada {ruta.name}")
