from __future__ import annotations

import re

from .layout import DEPT_CANON, fold

PAL_MINERIA = (
    "mina",
    "minas",
    "minera",
    "minero",
    "mineras",
    "mineros",
    "mineria",
    "concesion minera",
    "tajo",
    "relave",
    "relaves",
    "campamento minero",
    "unidad minera",
    "proyecto minero",
    "exploracion minera",
    "hidrocarburo",
    "hidrocarburos",
    "petroleo",
    "camisea",
    "gasoducto",
    "dorato",
    "antamina",
    "yanacocha",
    "las bambas",
    "southern",
    "chinalco",
    "barrick",
)

# Metales: solo palabra completa para no marcar "foro", "plataforma"
PAL_METAL = ("oro", "cobre", "zinc", "plata")


def flags(ficha: dict) -> dict:
    blob = fold(
        " ".join(
            str(ficha.get(k) or "")
            for k in (
                "tipo",
                "codigo",
                "caso",
                "ubicacion",
                "actores_primarios",
                "actores_secundarios",
                "actores",
                "texto_crudo",
            )
        )
    )
    # Evitar FP por el actor institucional "Ministerio de Energía y Minas".
    blob_mineria = re.sub(
        r"\benergia(?:\s+y|\s*,\s*|\s+e\s+)\s*minas\b", " ", blob
    )
    blob_mineria = re.sub(r"\bminem\b", " ", blob_mineria)
    tipo = fold(ficha.get("tipo") or "")
    socio = (
        "socioambiental" in tipo
        or "socio ambiental" in tipo
        or "sociambiental" in tipo  # typo frecuente de la Defensoría
    )
    mineria = any(re.search(rf"\b{re.escape(p)}\b", blob_mineria) for p in PAL_MINERIA)
    if not mineria:
        mineria = any(re.search(rf"\b{p}\b", blob_mineria) for p in PAL_METAL)
    return {
        "es_socioambiental": int(socio),
        "menciona_mineria": int(bool(mineria)),
    }


def completar_departamento(ficha: dict) -> dict:
    if ficha.get("departamento"):
        return ficha
    blob = fold((ficha.get("ubicacion") or "") + " " + (ficha.get("caso") or ""))
    # Nombres más largos primero
    for raw, canon in sorted(DEPT_CANON.items(), key=lambda x: -len(x[0])):
        if fold(raw) in blob:
            ficha["departamento"] = canon
            break
    return ficha
