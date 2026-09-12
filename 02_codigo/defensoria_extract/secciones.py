from __future__ import annotations

import re

from .layout import fold

INICIO_DETALLE = [
    r"detalle de los conflictos sociales activos",
    r"detalle de los conflictos activos",
    r"descripcion de los conflictos",
    r"conflictos activos desarrollados en un solo departamento",
    r"1\.1\s+conflictos activos",
    r"1\.\s*nuevos casos",
    r"conflictos vigentes",
    r"conflictos de distinta intensidad",
]

STOP = [
    r"acciones colectivas de protesta",
    r"hechos de violencia contra la vida",
    r"actuaciones defensoriales",
    r"acciones de violencia subversiva",
    r"alertas tempranas",
    r"otros indicadores",
    r"casos en observaci[oó]n",
    r"forma de resoluci[oó]n",
    r"n\.?\s*°?\s*fecha\s+medida\s+actores",
    r"n\.?\s*°?\s*lugar\s+caso\s+motivo",
]


def _match_any(texto: str, patrones: list[str]) -> bool:
    return any(re.search(p, texto) for p in patrones)


def pagina_inicia_detalle(texto: str) -> bool:
    t = re.sub(r"\s+", " ", fold(texto))
    ntipo = len(re.findall(r"tipo\s*:", t))
    if "sumilla" in t and ntipo < 3:
        return False
    if "informacion consolidada" in t and ntipo < 2:
        return False
    if "fecha de inicio" in t and "estado situacional" in t:
        return False
    if "detalle de los conflictos sociales activos" in t and (
        ntipo >= 1
        or "desarrollados en un solo departamento" in t
        or "en un departamento" in t
    ):
        return True
    if "detalle de los conflictos" in t and ntipo >= 2:
        return True
    if "anexo" in t and "descripcion de los conflictos" in t:
        return True
    if re.search(r"iii\.?\s+descripcion de los conflictos", t):
        return True
    if re.search(r"1\.1\.?\s+conflictos activos", t) and ntipo >= 2:
        return True
    if (
        ntipo >= 2
        and "la defensoria del pueblo da cuenta" in t
        and "conflictos activos" in t
    ):
        return True
    if re.search(r"1\.\s*conflictos activos", t) and "estado:" in t:
        return True
    if re.search(r"1\.\s*(?:nuevos casos|casos nuevos)", t):
        return True
    if "conflictos vigentes" in t and re.search(r"region\s+\w+", t):
        return True
    if "autoridad cuestionada" in t and "ubicacion" in t:
        return True
    if re.search(r"autoridad\s*:", t) and re.search(r"motivo\s*:", t):
        return True
    return False


def pagina_es_stop(texto: str, ya_detalle: bool) -> bool:
    if not ya_detalle:
        return False
    if "sumilla" in fold(texto)[:1500]:
        return False
    if re.search(r"(?i)tipo\s*:", texto):
        return False
    head = fold("\n".join((texto or "").splitlines()[:12]))
    return _match_any(head, STOP)


def estado_de_bloque(texto: str) -> str | None:
    t = re.sub(r"\s+", " ", fold(texto)).strip(" .:")
    # Encabezados largos (p. ej. "VII. DETALLE DE LOS CONFLICTOS LATENTES La Defensoría…")
    if "detalle de los conflictos latentes" in t[:120]:
        return "Latente"
    if "detalle de los conflictos sociales activos" in t[:120]:
        return "Activo"
    if len(t) > 220:
        return None
    if re.fullmatch(r"(?:\d+\.\d+\s+)?(?:detalle de los )?conflictos latentes", t):
        return "Latente"
    if re.fullmatch(r"(?:casos|conflictos) fusionados", t):
        return "Fusionado"
    if re.search(r"casos en observacion|conflictos inactivos", t) and len(t) < 80:
        return "Inactivo"
    if re.fullmatch(r"(?:\d+\.\d+\s+)?conflictos reactivados", t):
        return "Reactivado"
    if "desarrollados en mas de un departamento" in t:
        return "Activo"
    if re.fullmatch(
        r"(?:\d+\.\d+\s+)?conflictos activos(?: desarrollados en un solo departamento.*)?",
        t,
    ):
        return "Activo"
    if re.fullmatch(
        r"(?:\d+\.\d+\s+)?(?:conflictos resueltos|conflictos concluidos|casos resueltos)(?: o desactivados)?",
        t,
    ):
        return "Resuelto"
    if re.fullmatch(r"(?:\d+\.\s*)?nuevos casos", t):
        return "Nuevo"
    if re.fullmatch(r"(?:\d+\.\s*)?conflictos vigentes", t):
        return "Activo"
    return None


def pagina_es_latentes(texto: str) -> bool:
    """True si la página abre o continúa el detalle tabular de latentes."""
    t = fold(texto or "")
    if "detalle de los conflictos latentes" in t:
        return True
    # Continuación: cabecera de tabla compacta típica 2015–2026
    if re.search(r"n\.?\s*°?\s*ubicacion\s+caso", t[:800]):
        return True
    if re.search(
        r"n\.?\s*°?\s*fecha\s+de\s+inicio\s+departamento\s+denominacion",
        t[:800],
    ):
        return True
    return False
