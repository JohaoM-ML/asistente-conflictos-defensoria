"""Calcula la precisión del extractor a partir de la muestra dorada anotada.

Lee el XLSX que produce `generar_muestra_dorada.py` una vez que las columnas
ok_* están llenas, y reporta precisión por campo y por formato de maqueta. El
corte por formato es lo relevante: el extractor no falla parejo, falla en
épocas concretas, y saber en cuál orienta dónde vale la pena trabajar.

Uso:
    python -u 02_codigo/evaluar_extraccion.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from rutas import ENCODING_CSV, MUESTRA_DORADA, PRECISION_TXT

CAMPOS = ["caso", "tipo", "ubicacion", "actores", "departamento"]
SALIDA_TXT = PRECISION_TXT


def tasa(serie: pd.Series) -> tuple[int, int, float | None]:
    """Anotadas, correctas y precisión. Las celdas vacías no cuentan."""
    vals = pd.to_numeric(serie, errors="coerce").dropna()
    n = len(vals)
    if n == 0:
        return 0, 0, None
    ok = int((vals == 1).sum())
    return n, ok, 100.0 * ok / n


def fmt(valor: float | None) -> str:
    return "  s/d" if valor is None else f"{valor:5.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--muestra", type=Path, default=MUESTRA_DORADA)
    args = ap.parse_args()

    if not args.muestra.exists():
        print(f"No existe {args.muestra}.")
        print("Generarla con: python -u 02_codigo/generar_muestra_dorada.py")
        raise SystemExit(1)

    df = pd.read_excel(args.muestra, sheet_name="muestra")
    cols_ok = [f"ok_{c}" for c in CAMPOS if f"ok_{c}" in df.columns]
    anotadas = df[cols_ok].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)
    n_anot = int(anotadas.sum())

    lineas = [
        "PRECISIÓN DE EXTRACCIÓN — muestra dorada",
        f"Fichas en la muestra : {len(df)}",
        f"Fichas anotadas      : {n_anot}",
        "",
    ]
    if n_anot == 0:
        lineas.append("Sin anotaciones todavía: llenar las columnas ok_* del XLSX.")
        print("\n".join(lineas))
        raise SystemExit(0)

    lineas.append("Global por campo:")
    for campo in CAMPOS:
        col = f"ok_{campo}"
        if col not in df.columns:
            continue
        n, ok, p = tasa(df[col])
        lineas.append(f"  {campo:<14} {fmt(p)}  ({ok}/{n} anotadas)")

    lineas.append("")
    lineas.append("Por formato de maqueta:")
    cabecera = "  " + "formato".ljust(30) + "".join(c.rjust(13) for c in CAMPOS) + "     n"
    lineas.append(cabecera)
    lineas.append("  " + "-" * (len(cabecera) - 2))
    for fmt_nombre, g in df.groupby("formato"):
        fila = "  " + str(fmt_nombre).ljust(30)
        for campo in CAMPOS:
            col = f"ok_{campo}"
            _, _, p = tasa(g[col]) if col in g.columns else (0, 0, None)
            fila += fmt(p).rjust(13)
        lineas.append(fila + f"{len(g):6}")

    corregidos = df.get("caso_correcto_si_ok_caso_es_0")
    if corregidos is not None:
        n_corr = int(corregidos.dropna().astype(str).str.strip().ne("").sum())
        if n_corr:
            lineas.append("")
            lineas.append(f"Casos con texto corregido a mano: {n_corr}")

    texto = "\n".join(lineas) + "\n"
    SALIDA_TXT.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_TXT.write_text(texto, encoding=ENCODING_CSV)
    print(texto)
    print(f"Escrito: {SALIDA_TXT}")


if __name__ == "__main__":
    main()
