from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


def estandarizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for w in (
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "y",
        "en",
        "por",
        "con",
        "a",
        "un",
        "una",
        "que",
        "se",
        "al",
    ):
        t = re.sub(rf"\b{w}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _ratio(a: str, b: str) -> float:
    if fuzz is not None:
        return float(fuzz.token_sort_ratio(a, b))
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio() * 100


def agrupar(filas: list[dict], umbral: float = 88.0) -> list[dict]:
    """Asigna caso_id. Bloquea por departamento para no comparar n² nacional."""
    por: dict[str, list[int]] = defaultdict(list)
    claves = []
    for i, f in enumerate(filas):
        dept = (f.get("departamento") or "").upper() or "_"
        clave = estandarizar(f.get("caso") or "")
        claves.append(clave)
        por[dept].append(i)
        f["caso_estandarizado"] = clave

    next_id = 1
    asignado = {}
    for dept, idxs in por.items():
        reps: list[tuple[int, int]] = []  # (caso_id, index_rep)
        for i in idxs:
            c = claves[i]
            if not c:
                asignado[i] = next_id
                next_id += 1
                continue
            hallado = None
            for cid, j in reps:
                if _ratio(c, claves[j]) >= umbral:
                    hallado = cid
                    break
            if hallado is None:
                hallado = next_id
                next_id += 1
                reps.append((hallado, i))
            asignado[i] = hallado

    for i, f in enumerate(filas):
        f["caso_id"] = asignado.get(i, i + 1)
    return filas
