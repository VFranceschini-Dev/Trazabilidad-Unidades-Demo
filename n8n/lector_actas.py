"""Lectura de actas en PDF dentro de n8n: capa de texto con pdfplumber o, si no hay, Tesseract.

Lo ejecuta el flujo de actas: recibe la ruta del PDF e imprime los datos en JSON.

La confianza de cada campo es el promedio de las palabras que lo componen; la general, el
promedio de los campos encontrados. Un PDF ilegible no es un error: devuelve una lectura
vacia, para que el acta quede registrada y se cargue a mano (HU-08.4).
"""

from __future__ import annotations

import io
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
CONFIANZA_TEXTO = 99.0
MINIMO_CARACTERES_TEXTO = 30

_PATENTE = r"[A-Z]{2}\s?\d{3}\s?[A-Z]{2}|[A-Z]{3}\s?\d{3}"
_DIA = r"\d{2}[/-]\d{2}[/-]\d{4}"

_NRO_ACTA = re.compile(r"Acta(?:\s+de\s+infracci[oó]n)?\s*N\s*[°ºo0.]*\s*[:.]?\s*([A-Z0-9][A-Z0-9\-/]{3,29})", re.I)
_DOMINIO = re.compile(rf"(?:Dominio|Patente)\s*[:.]?\s*({_PATENTE})")
_PATENTE_SUELTA = re.compile(rf"\b({_PATENTE})\b")
_FECHA_HORA = re.compile(
    rf"Fecha(?!\s+de\s+(?:emisi[oó]n|vencimiento))(?:\s+y\s+hora)?(?:\s+de\s+la\s+infracci[oó]n)?\s*[:.]?\s*"
    rf"({_DIA})\s*[,-]?\s*(?:Hora\s*[:.]?\s*)?(\d{{2}}[:.]\d{{2}})",
    re.I,
)
_JURISDICCION = re.compile(r"Jurisdicci[oó]n\s*[:.]\s*([^\n]{3,80})", re.I)
_LUGAR = re.compile(r"Lugar\s*[:.]\s*([^\n]{3,80})", re.I)
_MONTO = re.compile(r"(?:Importe(?:\s+de\s+la\s+multa)?|Monto)\s*[:.]?\s*\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", re.I)
_VENCIMIENTO = re.compile(rf"(?:Fecha\s+de\s+)?vencimiento[^\d\n]{{0,30}}\s*({_DIA})", re.I)


@dataclass
class LecturaActa:
    nro_acta: Optional[str] = None
    patente: Optional[str] = None
    fecha_hora: Optional[datetime] = None
    jurisdiccion: Optional[str] = None
    monto: Optional[Decimal] = None
    vencimiento: Optional[date] = None
    confianza_campos: dict[str, float] = field(default_factory=dict)

    @property
    def confianza(self) -> Optional[float]:
        if not self.confianza_campos:
            return None
        return round(sum(self.confianza_campos.values()) / len(self.confianza_campos), 2)


def normalizar_patente(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def _dia(texto: str) -> date:
    return datetime.strptime(texto.replace("-", "/"), "%d/%m/%Y").date()


def _monto(texto: str) -> Optional[Decimal]:
    try:
        return Decimal(texto.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


class _Texto:
    """Texto de la pagina con la confianza de cada palabra, para promediar lo que coincide."""

    def __init__(self, palabras: list[tuple[str, float]]) -> None:
        self.texto = ""
        self._tramos: list[tuple[int, int, float]] = []
        for palabra, confianza in palabras:
            if palabra == "\n":
                self.texto = self.texto.rstrip(" ") + "\n"
                continue
            inicio = len(self.texto)
            self.texto += palabra + " "
            self._tramos.append((inicio, inicio + len(palabra), confianza))

    def confianza(self, inicio: int, fin: int) -> float:
        valores = [c for a, b, c in self._tramos if a < fin and b > inicio]
        return round(sum(valores) / len(valores), 2) if valores else 0.0


def _extraer(fuente: _Texto) -> LecturaActa:
    texto = fuente.texto
    lectura = LecturaActa()
    conf = lectura.confianza_campos

    if m := _NRO_ACTA.search(texto):
        lectura.nro_acta = m.group(1).upper()[:30]
        conf["nro_acta"] = fuente.confianza(*m.span(1))
    if m := _DOMINIO.search(texto) or _PATENTE_SUELTA.search(texto):
        lectura.patente = normalizar_patente(m.group(1))
        conf["patente"] = fuente.confianza(*m.span(1))
    if m := _FECHA_HORA.search(texto):
        try:
            dia = _dia(m.group(1))
            hora = datetime.strptime(m.group(2).replace(".", ":"), "%H:%M").time()
        except ValueError:
            pass
        else:
            lectura.fecha_hora = datetime.combine(dia, hora, ZONA)
            conf["fecha_hora"] = fuente.confianza(m.start(1), m.end(2))
    if m := _JURISDICCION.search(texto) or _LUGAR.search(texto):
        lectura.jurisdiccion = m.group(1).strip()[:80]
        conf["jurisdiccion"] = fuente.confianza(*m.span(1))
    if m := _MONTO.search(texto):
        lectura.monto = _monto(m.group(1))
        if lectura.monto is not None:
            conf["monto"] = fuente.confianza(*m.span(1))
    if m := _VENCIMIENTO.search(texto):
        try:
            lectura.vencimiento = _dia(m.group(1))
        except ValueError:
            pass
        else:
            conf["vencimiento"] = fuente.confianza(*m.span(1))
    return lectura


class LectorTesseract:
    """Primero la capa de texto; si no alcanza, 300 ppp y Tesseract en espanol."""

    def leer(self, contenido: bytes) -> LecturaActa:
        try:
            return _extraer(self._capa_de_texto(contenido) or self._ocr(contenido))
        except Exception:  # PDF danado o ilegible: se registra para carga manual (HU-08.4)
            return LecturaActa()

    def _capa_de_texto(self, contenido: bytes) -> Optional[_Texto]:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            texto = "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)
        if len(texto.strip()) < MINIMO_CARACTERES_TEXTO:
            return None
        palabras: list[tuple[str, float]] = []
        for linea in texto.splitlines():
            palabras += [(p, CONFIANZA_TEXTO) for p in linea.split()]
            palabras.append(("\n", 0.0))
        return _Texto(palabras)

    def _ocr(self, contenido: bytes) -> _Texto:
        palabras: list[tuple[str, float]] = []
        for imagen in convert_from_bytes(contenido, dpi=300):
            datos = pytesseract.image_to_data(imagen, lang="spa", output_type=pytesseract.Output.DICT)
            linea_actual = None
            for i, palabra in enumerate(datos["text"]):
                if not palabra.strip():
                    continue
                linea = (datos["block_num"][i], datos["par_num"][i], datos["line_num"][i])
                if linea_actual is not None and linea != linea_actual:
                    palabras.append(("\n", 0.0))
                linea_actual = linea
                palabras.append((palabra, max(float(datos["conf"][i]), 0.0)))
            palabras.append(("\n", 0.0))
        return _Texto(palabras)


def a_json(lectura: LecturaActa) -> str:
    return json.dumps(
        {
            "nro_acta": lectura.nro_acta,
            "patente": lectura.patente,
            "fecha_hora": lectura.fecha_hora.isoformat() if lectura.fecha_hora else None,
            "jurisdiccion": lectura.jurisdiccion,
            "monto": str(lectura.monto) if lectura.monto is not None else None,
            "vencimiento": lectura.vencimiento.isoformat() if lectura.vencimiento else None,
            "confianza_campos": lectura.confianza_campos,
        },
        ensure_ascii=False,
    )


if __name__ == "__main__":
    with open(sys.argv[1], "rb") as archivo:
        print(a_json(LectorTesseract().leer(archivo.read())))
