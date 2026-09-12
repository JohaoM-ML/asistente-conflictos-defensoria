from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import fitz

DEPT_CANON = {
    "AMAZONAS": "Amazonas",
    "ANCASH": "Áncash",
    "ÁNCASH": "Áncash",
    "APURIMAC": "Apurímac",
    "APURÍMAC": "Apurímac",
    "AREQUIPA": "Arequipa",
    "AYACUCHO": "Ayacucho",
    "CAJAMARCA": "Cajamarca",
    "CALLAO": "Callao",
    "CUSCO": "Cusco",
    "CUZCO": "Cusco",
    "HUANCAVELICA": "Huancavelica",
    "HUANUCO": "Huánuco",
    "HUÁNUCO": "Huánuco",
    "ICA": "Ica",
    "JUNIN": "Junín",
    "JUNÍN": "Junín",
    "LA LIBERTAD": "La Libertad",
    "LAMBAYEQUE": "Lambayeque",
    "LIMA METROPOLITANA": "Lima Metropolitana",
    "LIMA PROVINCIAS": "Lima Provincias",
    "LIMA": "Lima",
    "LORETO": "Loreto",
    "MADRE DE DIOS": "Madre de Dios",
    "MOQUEGUA": "Moquegua",
    "PASCO": "Pasco",
    "PIURA": "Piura",
    "PUNO": "Puno",
    "SAN MARTIN": "San Martín",
    "SAN MARTÍN": "San Martín",
    "TACNA": "Tacna",
    "TUMBES": "Tumbes",
    "UCAYALI": "Ucayali",
    "MULTIRREGIONAL": "Multirregional",
    "MULTIDEPARTAMENTAL": "Multidepartamental",
    "NACIONAL": "Nacional",
}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def norm_ws(s: str) -> str:
    s = (s or "").replace("\u00ad", "")
    s = re.sub(r"[ \t\r]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def es_encabezado_pagina(txt: str) -> bool:
    t = re.sub(r"\s+", " ", fold(txt)).strip()
    if "reporte mensual de conflictos" in t or "reporte de conflictos sociales n" in t:
        return True
    if "adjuntia para la prevencion" in t or "subadjuntia para la prevencion" in t:
        return True
    if "direccion de la unidad de conflictos" in t:
        return True
    if t in {
        "descripcion",
        "hechos del mes",
        "estado actual",
        "descripcion hechos del mes",
        "descripcion estado actual",
        "n",
        "departamento",
    }:
        return True
    return False


def es_departamento(txt: str) -> str | None:
    t = unicodedata.normalize("NFKC", txt or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^REGI[OÓ]N\s+", "", t, flags=re.I)
    t = re.sub(r"[^A-ZÁÉÍÓÚÜÑ /]", "", t.upper()).strip()
    t = (
        t.replace("ÁNCASH", "ANCASH")
        .replace("APURÍMAC", "APURIMAC")
        .replace("HUÁNUCO", "HUANUCO")
        .replace("JUNÍN", "JUNIN")
        .replace("SAN MARTÍN", "SAN MARTIN")
    )
    if t in DEPT_CANON:
        return DEPT_CANON[t]
    # "AREQUIPA / PUNO"
    partes = [p.strip() for p in t.split("/") if p.strip()]
    if len(partes) >= 2 and all(p in DEPT_CANON or p.replace("ÁNCASH", "ANCASH") in DEPT_CANON for p in partes):
        return " / ".join(DEPT_CANON.get(p, p.title()) for p in partes)
    return None


@dataclass
class Bloque:
    pagina: int
    y: float
    x0: float
    x1: float
    col: str
    texto: str


# Corte L/R entre la columna de descripción y la de hechos del mes. Se probó
# detectarlo por página con el mayor hueco entre centros x de los bloques y
# degradó todas las métricas frente a este valor fijo (menos fichas y menos
# cobertura de caso, ubicacion y actores), así que se mantiene constante.
SPLIT_DEFECTO = 300.0


def bloques_pagina(
    page: fitz.Page, pagina: int, split_mid: float = SPLIT_DEFECTO
) -> list[Bloque]:
    header = 55.0
    footer = page.rect.height - 50.0
    out: list[Bloque] = []
    data = page.get_text("dict") or {}
    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        x0, y0, x1, y1 = block["bbox"]
        if y1 < header or y0 > footer:
            continue
        partes = []
        for line in block.get("lines", []) or []:
            partes.append("".join(sp.get("text") or "" for sp in line.get("spans", []) or []))
        txt = norm_ws("\n".join(partes))
        if not txt or es_encabezado_pagina(txt):
            continue
        if len(txt) <= 3 and txt.isdigit():
            continue
        mid = (x0 + x1) / 2.0
        col = "L" if mid < split_mid else "R"
        out.append(Bloque(pagina, y0, x0, x1, col, txt))
    out.sort(key=lambda b: (b.y, 0 if b.col == "L" else 1, b.x0))
    return out


def texto_pagina_simple(page: fitz.Page) -> str:
    return norm_ws(page.get_text("text") or "")


def abrir(path) -> fitz.Document:
    return fitz.open(path)
