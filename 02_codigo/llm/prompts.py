"""Prompt versionado. El texto entra al hash de caché vía llm.PROMPT_VERSION."""

SISTEMA = """Eres un asistente de investigación que resume fichas de conflictos sociales de la Defensoría del Pueblo del Perú.

Reglas:
- Usa SOLO el texto que te entregan. No inventes empresas, lugares, minerales ni fechas.
- Si un dato no aparece, deja la cadena vacía. No pongas "no especificado".
- El resumen tiene dos o tres oraciones en español, en tercera persona.
- No copies el texto a medias ni cortes a mitad de palabra.
- Si el insumo es un marcador ("NUEVO", "REACTIVADO"), un encabezado o texto ilegible, pon texto_ilegible=true, confianza=baja y un resumen vacío.
- tipo_normalizado: socioambiental, laboral, comunal, gobierno_local, gobierno_nacional, demarcacion u otros.
"""


def armar_usuario(meta: dict, texto: str) -> str:
    partes = [
        f"Departamento: {meta.get('departamento') or '(sin dato)'}",
        f"Tipo en la ficha: {meta.get('tipo') or '(sin dato)'}",
        f"Ubicación: {meta.get('ubicacion') or '(sin dato)'}",
        f"Actores: {meta.get('actores') or '(sin dato)'}",
        f"Meses cubiertos: {meta.get('n_meses') or '?'}",
        "",
        "Texto de la ficha (columna de descripción y hechos del mes):",
        texto.strip(),
    ]
    return "\n".join(partes)
