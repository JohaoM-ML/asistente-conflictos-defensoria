"""Rutas del proyecto Asistente. Un solo sitio para no hardcodear carpetas."""
from __future__ import annotations

from pathlib import Path

CODIGO = Path(__file__).resolve().parent
RAIZ = CODIGO.parent
DATOS = RAIZ / "01_datos"
PDFS = DATOS / "crudos" / "pdfs"
PDFS_POR_FORMATO = DATOS / "crudos" / "pdfs_por_formato"
INVENTARIO = DATOS / "inventario"
PROCESADOS = DATOS / "procesados" / "conflictos"
DESCARGA_PARCIAL = RAIZ / "99_archivo" / "descarga_web_parcial"

FORMATOS_CSV = INVENTARIO / "formatos_pdf_defensoria.csv"
FECHAS_CSV = INVENTARIO / "fechas.csv"
INVENTARIO_CSV = INVENTARIO / "inventario.csv"

PANEL_CSV = PROCESADOS / "panel_caso_mes.csv"
PANEL_CSV_GZ = PROCESADOS / "panel_caso_mes.csv.gz"
CASOS_UNICOS_CSV = PROCESADOS / "casos_unicos.csv"
CASOS_UNICOS_XLSX = PROCESADOS / "casos_unicos_resumen.xlsx"


def ruta_panel() -> Path:
    """CSV local si existe; si no, el .gz que sí entra en GitHub. pandas lee ambos."""
    if PANEL_CSV.exists() and PANEL_CSV.stat().st_size > 0:
        return PANEL_CSV
    if PANEL_CSV_GZ.exists() and PANEL_CSV_GZ.stat().st_size > 0:
        return PANEL_CSV_GZ
    raise FileNotFoundError(
        "No está el panel. En un clon: debe existir "
        "01_datos/procesados/conflictos/panel_caso_mes.csv.gz. "
        "Para reconstruirlo: python -u 02_codigo/extraer_conflictos.py"
    )

# Capa LLM (aditiva: no interviene en la extracción determinista).
RESUMENES_LLM = PROCESADOS / "resumenes_llm.csv"
CACHE_LLM = PROCESADOS / "cache_llm.sqlite"

# Control de calidad: comparaciones y muestra anotada. No son el panel.
CALIDAD = PROCESADOS / "calidad"
MUESTRA_DORADA = CALIDAD / "muestra_dorada.xlsx"
COMPARACION_IDENTIDAD = CALIDAD / "comparacion_identidad.txt"
PRECISION_TXT = CALIDAD / "precision_extraccion.txt"
CONFLICTO_RECREADO_CSV = CALIDAD / "conflicto_recreado.csv"
CONFLICTO_RECREADO_XLSX = CALIDAD / "conflicto_recreado.xlsx"
COMPARACION_DRIVE = CALIDAD / "comparacion_conflicto_drive.txt"

# Copias viejas del panel. No usar para análisis.
RESPALDOS = RAIZ / "99_archivo" / "respaldos"

ENV_FILE = RAIZ / ".env"

# Excel muestra caracteres rotos ante UTF-8 sin BOM.
ENCODING_CSV = "utf-8-sig"
