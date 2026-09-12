"""Capa aditiva: resume cada caso_id con Gemini y escribe resumenes_llm.csv.

No relee los PDF ni cambia el panel. Lee panel_caso_mes.csv, llama al modelo
una vez por caso (no por fila-mes) y guarda el resultado junto a una caché
SQLite para que las re-corridas no vuelvan a pagar.

Uso:
    python -u 02_codigo/enriquecer_llm.py --limite 8
    python -u 02_codigo/enriquecer_llm.py --solo-mineria
    python -u 02_codigo/enriquecer_llm.py
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from llm import PROMPT_VERSION
from llm.cache import CacheLLM
from llm.cliente import cargar_env, crear_cliente, llamar, modelo_nombre
from llm.esquema import CAMPOS, vacio
from llm.prompts import armar_usuario
from rutas import (
    CACHE_LLM,
    CASOS_UNICOS_CSV,
    CASOS_UNICOS_XLSX,
    ENCODING_CSV,
    ENV_FILE,
    RESUMENES_LLM,
    ruta_panel,
)

MAX_TEXTO = 8000
COLS_SALIDA = [
    "caso_id",
    *CAMPOS,
    "modelo",
    "prompt_version",
    "hash_entrada",
    "fuente",
    "fecha_generacion",
]


def _es_mineria(df: pd.DataFrame) -> pd.Series:
    socio = df["es_socioambiental"].fillna("").astype(str).isin({"1", "True", "true"})
    mina = df["menciona_mineria"].fillna("").astype(str).isin({"1", "True", "true"})
    return socio | mina


def _pick_longest(series: pd.Series) -> str:
    vals = [str(v).strip() for v in series.tolist() if str(v).strip() and str(v).lower() != "nan"]
    return max(vals, key=len) if vals else ""


def _muestra_hechos(series: pd.Series) -> str:
    vals = [str(v).strip() for v in series.tolist() if str(v).strip() and str(v).lower() != "nan"]
    if not vals:
        return ""
    if len(vals) == 1:
        return vals[0]
    medio = vals[len(vals) // 2]
    partes = [vals[0], medio, vals[-1]]
    vistos: list[str] = []
    for p in partes:
        if p not in vistos:
            vistos.append(p)
    return "\n---\n".join(vistos)


def construir_insumos(panel: pd.DataFrame) -> list[dict]:
    insumos = []
    for cid, g in panel.groupby("caso_id", sort=False):
        crudo = _pick_longest(g["texto_crudo"])
        caso = _pick_longest(g["caso"])
        hechos = _muestra_hechos(g["hechos_del_mes"])
        cuerpo = "\n\n".join(p for p in (crudo or caso, hechos) if p)
        cuerpo = cuerpo[:MAX_TEXTO]
        actores = _pick_longest(g["actores_primarios"]) or _pick_longest(g["actores"])
        meta = {
            "caso_id": str(cid),
            "departamento": _pick_longest(g["departamento"]),
            "tipo": _pick_longest(g["tipo"]),
            "ubicacion": _pick_longest(g["ubicacion"]),
            "actores": actores,
            "n_meses": int(g[["anio", "mes"]].drop_duplicates().shape[0]),
        }
        usuario = armar_usuario(meta, cuerpo)
        clave = hashlib.sha256(
            f"{modelo_nombre()}|{PROMPT_VERSION}|{usuario}".encode("utf-8")
        ).hexdigest()
        insumos.append({"meta": meta, "usuario": usuario, "hash": clave})
    return insumos


def _fila(meta: dict, obj: dict, clave: str, fuente: str) -> dict:
    out = {"caso_id": meta["caso_id"]}
    out.update(obj)
    out["texto_ilegible"] = int(bool(obj.get("texto_ilegible")))
    out["modelo"] = modelo_nombre()
    out["prompt_version"] = PROMPT_VERSION
    out["hash_entrada"] = clave
    out["fuente"] = fuente
    out["fecha_generacion"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def _escribir(filas: list[dict], destino: Path) -> None:
    df = pd.DataFrame(filas)
    for c in COLS_SALIDA:
        if c not in df.columns:
            df[c] = ""
    df = df[COLS_SALIDA]
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False, encoding=ENCODING_CSV)


def _excel_str(valor) -> str:
    """Excel rechaza caracteres de control que a veces vienen del PDF."""
    if valor is None:
        return ""
    s = str(valor)
    return "".join(ch for ch in s if ch == "\t" or ch == "\n" or ord(ch) >= 32)


def escribir_excel_resumen(unicos: pd.DataFrame, destino: Path | None = None) -> Path:
    """Excel de casos únicos donde 'caso' es solo el resumen del LLM."""
    destino = destino or CASOS_UNICOS_XLSX
    df = unicos.copy()
    resumen = df["resumen_llm"] if "resumen_llm" in df.columns else df.get("resumen")
    if resumen is None:
        raise ValueError("Falta la columna resumen_llm")
    df["caso"] = resumen.fillna("").astype(str).str.strip()
    cols = [
        "caso_id",
        "caso",
        "departamento",
        "tipo",
        "tipo_normalizado",
        "n_meses",
        "es_socioambiental",
        "menciona_mineria",
        "empresa",
        "mineral",
        "comunidades",
        "demanda_principal",
        "confianza",
        "texto_ilegible",
    ]
    df = df[[c for c in cols if c in df.columns]]
    for c in df.columns:
        df[c] = df[c].map(_excel_str)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(destino, engine="openpyxl") as xls:
        df.to_excel(xls, sheet_name="casos", index=False)
        hoja = xls.sheets["casos"]
        hoja.freeze_panes = "A2"
        anchos = {"caso": 80, "comunidades": 28, "demanda_principal": 40, "departamento": 16}
        for i, col in enumerate(df.columns, start=1):
            letra = hoja.cell(row=1, column=i).column_letter
            hoja.column_dimensions[letra].width = anchos.get(col, 14)
    return destino


def unir_casos_unicos(resumenes: pd.DataFrame) -> None:
    if not CASOS_UNICOS_CSV.exists():
        return
    unicos = pd.read_csv(CASOS_UNICOS_CSV, dtype=str, keep_default_na=False)
    extra = resumenes[
        ["caso_id", "resumen", "empresa", "mineral", "comunidades",
         "demanda_principal", "tipo_normalizado", "confianza", "texto_ilegible"]
    ].rename(columns={"resumen": "resumen_llm"})
    # Quitar columnas de una corrida anterior para no duplicarlas.
    drop = [c for c in extra.columns if c != "caso_id" and c in unicos.columns]
    if drop:
        unicos = unicos.drop(columns=drop)
    unicos["caso_id"] = unicos["caso_id"].astype(str)
    extra["caso_id"] = extra["caso_id"].astype(str)
    out = unicos.merge(extra, on="caso_id", how="left")
    out.to_csv(CASOS_UNICOS_CSV, index=False, encoding=ENCODING_CSV)
    escribir_excel_resumen(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--solo-mineria", action="store_true")
    ap.add_argument("--hilos", type=int, default=0)
    ap.add_argument("--forzar", action="store_true", help="ignorar caché")
    args = ap.parse_args()

    cargar_env(ENV_FILE)
    hilos = args.hilos or int(os.environ.get("GEMINI_HILOS") or 8)

    panel = pd.read_csv(ruta_panel(), dtype=str, keep_default_na=False)
    if args.solo_mineria:
        panel = panel[_es_mineria(panel)].copy()
        print(f"Filtro minería: {len(panel)} filas", flush=True)

    insumos = construir_insumos(panel)
    if args.limite:
        insumos = insumos[: args.limite]
    print(
        f"{len(insumos)} casos -> Gemini ({modelo_nombre()}, {hilos} hilos, prompt {PROMPT_VERSION})",
        flush=True,
    )

    cache = CacheLLM(CACHE_LLM)
    cliente = crear_cliente()
    resultados: dict[str, dict] = {}

    pendientes = []
    for item in insumos:
        if not args.forzar:
            hit = cache.get(item["hash"])
            if hit is not None:
                resultados[item["meta"]["caso_id"]] = _fila(
                    item["meta"], hit, item["hash"], "cache"
                )
                continue
        pendientes.append(item)

    print(f"En caché: {len(insumos) - len(pendientes)}  Por llamar: {len(pendientes)}", flush=True)

    def trabajo(item: dict) -> tuple[str, dict]:
        obj = llamar(cliente, item["usuario"])
        cache.put(item["hash"], obj, modelo_nombre(), PROMPT_VERSION)
        fila = _fila(item["meta"], obj, item["hash"], "gemini")
        return item["meta"]["caso_id"], fila

    ok = err = 0
    if pendientes:
        with ThreadPoolExecutor(max_workers=max(1, hilos)) as pool:
            futuros = {pool.submit(trabajo, it): it for it in pendientes}
            for i, fut in enumerate(as_completed(futuros), 1):
                item = futuros[fut]
                cid = item["meta"]["caso_id"]
                try:
                    cid, fila = fut.result()
                    resultados[cid] = fila
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    resultados[cid] = _fila(item["meta"], vacio(), item["hash"], f"error:{exc}")
                    err += 1
                    print(f"  ERROR caso_id={cid}: {exc}", flush=True)
                if i % 25 == 0 or i == len(pendientes):
                    print(f"  [{i}/{len(pendientes)}] ok={ok} err={err}", flush=True)
                    filas_parcial = [resultados[it["meta"]["caso_id"]] for it in insumos if it["meta"]["caso_id"] in resultados]
                    _escribir(filas_parcial, RESUMENES_LLM)

    filas = [resultados[it["meta"]["caso_id"]] for it in insumos]
    _escribir(filas, RESUMENES_LLM)
    unir_casos_unicos(pd.DataFrame(filas))
    cache.close()

    df = pd.DataFrame(filas)
    n_baja = int((df["confianza"] == "baja").sum()) if len(df) else 0
    n_ileg = int(pd.to_numeric(df["texto_ilegible"], errors="coerce").fillna(0).sum()) if len(df) else 0
    print(
        f"Listo: {len(filas)} filas en {RESUMENES_LLM}\n"
        f"  llamadas nuevas: {ok}  errores: {err}  confianza baja: {n_baja}  texto_ilegible: {n_ileg}"
    )


if __name__ == "__main__":
    main()
