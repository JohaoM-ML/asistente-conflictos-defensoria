"""Comprueba que el clon puede reproducir el proyecto.

Uso (desde la raíz):
    python -u 02_codigo/comprobar_entorno.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from rutas import (  # noqa: E402
    CASOS_UNICOS_CSV,
    FORMATOS_CSV,
    PANEL_CSV,
    PANEL_CSV_GZ,
    PDFS,
    RAIZ,
    RESUMENES_LLM,
    ruta_panel,
)


def _ok(nombre: str, cond: bool, detalle: str = "") -> bool:
    marca = "OK  " if cond else "FALTA"
    extra = f"  ({detalle})" if detalle else ""
    print(f"  {marca}  {nombre}{extra}")
    return cond


def main() -> int:
    print(f"Raíz: {RAIZ}")
    print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
    print()

    print("Dependencias")
    mods = [
        ("fitz", "PyMuPDF"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("openpyxl", "openpyxl"),
        ("rapidfuzz", "rapidfuzz"),
        ("sklearn", "scikit-learn"),
        ("dotenv", "python-dotenv"),
    ]
    fallos = 0
    for mod, etiqueta in mods:
        try:
            __import__(mod)
            _ok(etiqueta, True)
        except ImportError:
            _ok(etiqueta, False, f"pip install -r {RAIZ / 'requirements.txt'}")
            fallos += 1

    try:
        __import__("sentence_transformers")
        _ok("sentence-transformers", True)
    except ImportError:
        _ok(
            "sentence-transformers",
            False,
            "hace falta para re-extraer con embeddings; no para leer el panel",
        )

    print()
    print("Datos versionados (sin PDF)")
    _ok("inventario de formatos", FORMATOS_CSV.exists(), str(FORMATOS_CSV))
    _ok("casos únicos", CASOS_UNICOS_CSV.exists(), str(CASOS_UNICOS_CSV))
    _ok("panel .gz (GitHub)", PANEL_CSV_GZ.exists(), str(PANEL_CSV_GZ))
    _ok("panel .csv local", PANEL_CSV.exists(), "opcional; pandas también lee el .gz")
    try:
        panel = ruta_panel()
        _ok("panel legible", True, str(panel))
    except FileNotFoundError as exc:
        _ok("panel legible", False, str(exc))
        fallos += 1
    _ok("resúmenes Gemini", RESUMENES_LLM.exists(), "capa opcional")

    print()
    print("Corpus PDF (solo si vas a extraer de nuevo)")
    n_pdf = len(list(PDFS.glob("*.pdf"))) if PDFS.exists() else 0
    _ok(
        f"PDF en crudos/pdfs: {n_pdf}",
        True,
        "esperado ~271 si quieres el universo; 0 sirve para solo analizar",
    )

    print()
    if fallos:
        print(f"Hay {fallos} cosa(s) por instalar o completar. Ver README.md.")
        return 1
    print("Entorno listo. Para analizar: 02_codigo/leer_panel_caso_mes.ipynb")
    print("Para re-extraer: python -u 02_codigo/extraer_conflictos.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
