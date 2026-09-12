"""Genera una muestra estratificada de fichas para anotar a mano.

RESUMEN.txt cuenta cuántas fichas salieron, no si están bien. Con siete
maquetas distintas repartidas en veintidós años la calidad varía mucho por
época, y sin una muestra anotada no hay forma de saber dónde falla el
extractor. Este script produce el archivo a llenar; `evaluar_extraccion.py`
lee el resultado y calcula la precisión.

Se incluye `texto_crudo` para poder verificar sin abrir el PDF, y el número de
reporte con la página para cuando haga falta ir a la fuente.

Uso:
    python -u 02_codigo/generar_muestra_dorada.py
    python -u 02_codigo/generar_muestra_dorada.py --n 200 --semilla 7
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from rutas import MUESTRA_DORADA, ruta_panel

# El anotador marca 1 (correcto) o 0 (incorrecto) en cada columna ok_*.
COLS_ANOTACION = [
    "ok_caso",
    "ok_tipo",
    "ok_ubicacion",
    "ok_actores",
    "ok_departamento",
    "caso_correcto_si_ok_caso_es_0",
    "notas",
]

COLS_CONTEXTO = [
    "caso_id",
    "numero_reporte",
    "anio",
    "mes",
    "formato",
    "archivo",
    "pagina",
    "estado",
    "departamento",
    "tipo",
    "caso",
    "ubicacion",
    "actores_primarios",
    "actores",
    "ingreso_como",
    "texto_crudo",
]

ANCHOS = {"caso": 70, "texto_crudo": 90, "ubicacion": 40, "actores": 40, "notas": 40}


def muestrear(df: pd.DataFrame, n: int, semilla: int, piso: int | None = None) -> pd.DataFrame:
    """Reparte n filas entre formatos, proporcional pero con piso por formato.

    Sin piso, las maquetas raras (lista_narrativa_2004 aporta pocas fichas)
    nunca entrarían en la muestra, y son justo las que más dudas generan.
    """
    formatos = df["formato"].value_counts()
    if piso is None:
        piso = max(30, n // (len(formatos) * 2))
    cuotas = {}
    for fmt, cuenta in formatos.items():
        cuotas[fmt] = max(piso, round(n * cuenta / len(df)))
    partes = []
    for fmt, cuota in cuotas.items():
        sub = df[df["formato"] == fmt]
        partes.append(sub.sample(n=min(cuota, len(sub)), random_state=semilla))
    return pd.concat(partes).sample(frac=1.0, random_state=semilla)


def escribir_xlsx(muestra: pd.DataFrame, destino: Path) -> None:
    with pd.ExcelWriter(destino, engine="openpyxl") as xls:
        muestra.to_excel(xls, sheet_name="muestra", index=False)
        hoja = xls.sheets["muestra"]
        for i, col in enumerate(muestra.columns, start=1):
            letra = hoja.cell(row=1, column=i).column_letter
            hoja.column_dimensions[letra].width = ANCHOS.get(col, 16)
        hoja.freeze_panes = "A2"

        guia = pd.DataFrame(
            {
                "instruccion": [
                    "Marcar 1 si el campo extraído es correcto, 0 si es incorrecto.",
                    "Dejar la celda vacía si el campo no aplica a esa maqueta.",
                    "Comparar contra texto_crudo; ir al PDF solo si hay duda.",
                    "El PDF está en 01_datos/crudos/pdfs con el nombre de 'archivo'.",
                    "Si ok_caso es 0, escribir el texto correcto en la columna de al lado.",
                    "Al terminar, correr: python -u 02_codigo/evaluar_extraccion.py",
                ]
            }
        )
        guia.to_excel(xls, sheet_name="instrucciones", index=False)
        xls.sheets["instrucciones"].column_dimensions["A"].width = 90


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument(
        "--piso",
        type=int,
        default=30,
        help="mínimo de fichas por formato de maqueta",
    )
    ap.add_argument("--salida", type=Path, default=MUESTRA_DORADA)
    args = ap.parse_args()

    if args.salida.exists():
        print(f"AVISO: {args.salida} ya existe y sería sobrescrito.")
        print("Renombrarlo antes de regenerar, o pasar --salida con otro nombre.")
        raise SystemExit(1)

    df = pd.read_csv(ruta_panel(), dtype=str, keep_default_na=False)
    muestra = muestrear(df, args.n, args.semilla, piso=args.piso)[COLS_CONTEXTO].copy()
    for col in COLS_ANOTACION:
        muestra[col] = ""

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    escribir_xlsx(muestra, args.salida)

    print(f"Muestra de {len(muestra)} fichas escrita en {args.salida}")
    print("\nReparto por formato:")
    print(muestra["formato"].value_counts().to_string())


if __name__ == "__main__":
    main()
