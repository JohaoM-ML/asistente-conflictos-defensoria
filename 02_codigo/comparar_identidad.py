"""Compara la identidad de casos por fuzzy contra la de embeddings.

Trabaja sobre `panel_caso_mes.csv` ya extraído, así que no hace falta releer los
PDF. Sirve para calibrar el umbral y, sobre todo, para revisar a mano las
fusiones más grandes antes de adoptar el método: un umbral bajo junta
conflictos distintos del mismo departamento y eso es peor que fragmentarlos.

Uso:
    python -u 02_codigo/comparar_identidad.py
    python -u 02_codigo/comparar_identidad.py --umbrales 0.82 0.86 0.90
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from defensoria_extract import identidad_emb
from rutas import COMPARACION_IDENTIDAD, ENCODING_CSV, ruta_panel

SALIDA_TXT = COMPARACION_IDENTIDAD


def resumen(tam: Counter, etiqueta: str) -> list[str]:
    n = len(tam)
    vals = sorted(tam.values())
    un_mes = sum(1 for v in vals if v == 1)
    return [
        f"{etiqueta}:",
        f"  casos únicos      : {n}",
        f"  de un solo mes    : {un_mes} ({100 * un_mes / n:.1f}%)",
        f"  mediana de meses  : {vals[n // 2]}",
        f"  máximo de meses   : {vals[-1]}",
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbrales", type=float, nargs="+", default=[0.82, 0.86, 0.90])
    ap.add_argument("--ejemplos", type=int, default=15)
    args = ap.parse_args()

    df = pd.read_csv(ruta_panel(), dtype=str, keep_default_na=False)
    print(f"Panel: {len(df)} filas", flush=True)

    filas = df.to_dict("records")
    fuzzy_ids = df["caso_id"].tolist()
    lineas: list[str] = ["COMPARACIÓN DE IDENTIDAD DE CASOS", ""]
    lineas += resumen(Counter(fuzzy_ids), "Fuzzy actual (rapidfuzz, umbral 88)")
    lineas.append("")

    for umbral in args.umbrales:
        print(f"\n=== embeddings, umbral {umbral} ===", flush=True)
        copia = [dict(f) for f in filas]
        identidad_emb.agrupar(copia, umbral=umbral, verbose=False)
        nuevos = [f["caso_id"] for f in copia]
        lineas += resumen(Counter(nuevos), f"Embeddings (umbral {umbral})")

        # Fusiones: un caso nuevo que absorbe varios casos fuzzy distintos.
        por_nuevo: dict[int, set] = {}
        for nid, fid in zip(nuevos, fuzzy_ids):
            por_nuevo.setdefault(nid, set()).add(fid)
        fusiones = sorted(por_nuevo.items(), key=lambda kv: -len(kv[1]))
        lineas.append(
            f"  fusiones (1 caso nuevo <- varios fuzzy): "
            f"{sum(1 for _, s in fusiones if len(s) > 1)}"
        )
        lineas.append("")
        lineas.append(f"  Fusiones más grandes (revisar a mano, umbral {umbral}):")
        for nid, viejos in fusiones[: args.ejemplos]:
            if len(viejos) < 2:
                break
            textos = [
                c["caso"][:110]
                for c in copia
                if c["caso_id"] == nid and c.get("caso")
            ]
            vistos: list[str] = []
            for t in textos:
                if t not in vistos:
                    vistos.append(t)
            dept = next(
                (c.get("departamento") for c in copia if c["caso_id"] == nid), ""
            )
            lineas.append(f"    [{dept}] {len(viejos)} casos fuzzy -> 1")
            for t in vistos[:4]:
                lineas.append(f"       - {t}")
            lineas.append("")
        lineas.append("")

    SALIDA_TXT.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_TXT.write_text("\n".join(lineas), encoding=ENCODING_CSV)
    print("\n".join(lineas))
    print(f"\nEscrito: {SALIDA_TXT}")


if __name__ == "__main__":
    main()
