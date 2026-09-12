"""Esquema JSON que Gemini debe devolver por caso."""

CAMPOS = [
    "resumen",
    "empresa",
    "mineral",
    "comunidades",
    "demanda_principal",
    "tipo_normalizado",
    "confianza",
    "texto_ilegible",
]

TIPOS_NORMALIZADOS = [
    "socioambiental",
    "laboral",
    "comunal",
    "gobierno_local",
    "gobierno_nacional",
    "demarcacion",
    "otros",
]

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "resumen": {
            "type": "STRING",
            "description": "Dos o tres oraciones en español. Quién, dónde, de qué se trata el conflicto.",
        },
        "empresa": {
            "type": "STRING",
            "description": "Empresa o proyecto citado, o cadena vacía.",
        },
        "mineral": {
            "type": "STRING",
            "description": "Mineral o recurso (cobre, oro, petróleo, agua, etc.) o cadena vacía.",
        },
        "comunidades": {
            "type": "STRING",
            "description": "Comunidades, distritos o poblaciones, separados por '; '.",
        },
        "demanda_principal": {
            "type": "STRING",
            "description": "Qué piden o a qué se oponen, en una oración.",
        },
        "tipo_normalizado": {
            "type": "STRING",
            "enum": TIPOS_NORMALIZADOS,
        },
        "confianza": {
            "type": "STRING",
            "enum": ["alta", "media", "baja"],
            "description": "Alta si el texto alcanza para entender el conflicto.",
        },
        "texto_ilegible": {
            "type": "BOOLEAN",
            "description": "True si el insumo está cortado, mezclado o no describe un conflicto.",
        },
    },
    "required": CAMPOS,
}


def vacio() -> dict:
    return {
        "resumen": "",
        "empresa": "",
        "mineral": "",
        "comunidades": "",
        "demanda_principal": "",
        "tipo_normalizado": "otros",
        "confianza": "baja",
        "texto_ilegible": True,
    }


def normalizar(obj: dict) -> dict:
    out = vacio()
    if not isinstance(obj, dict):
        return out
    out["resumen"] = str(obj.get("resumen") or "").strip()
    out["empresa"] = str(obj.get("empresa") or "").strip()
    out["mineral"] = str(obj.get("mineral") or "").strip()
    out["comunidades"] = str(obj.get("comunidades") or "").strip()
    out["demanda_principal"] = str(obj.get("demanda_principal") or "").strip()
    tipo = str(obj.get("tipo_normalizado") or "").strip().lower()
    out["tipo_normalizado"] = tipo if tipo in TIPOS_NORMALIZADOS else "otros"
    conf = str(obj.get("confianza") or "").strip().lower()
    out["confianza"] = conf if conf in {"alta", "media", "baja"} else "baja"
    ileg = obj.get("texto_ilegible")
    if isinstance(ileg, str):
        out["texto_ilegible"] = ileg.strip().lower() in {"true", "1", "si", "sí", "yes"}
    else:
        out["texto_ilegible"] = bool(ileg)
    if not out["resumen"]:
        out["confianza"] = "baja"
        out["texto_ilegible"] = True
    return out
