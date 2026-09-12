"""Caracteriza el formato de cada PDF de la serie Defensoría (portada + estructura)."""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import fitz

from rutas import FECHAS_CSV as FECHAS
from rutas import FORMATOS_CSV as OUT
from rutas import INVENTARIO, PDFS, PDFS_POR_FORMATO

DEST = PDFS
OUT_JSON = INVENTARIO / "formatos_pdf_defensoria.json"
MUESTRA = INVENTARIO / "formatos_pdf_muestras.txt"
GRUPOS = PDFS_POR_FORMATO

CARPETAS = {
    "lista_narrativa_2004": "01_lista_narrativa_abr2004",
    "reporte_n_tabla_regiones": "02_reporte_N_tabla_2004_2006",
    "unidad_reporte_n": "03_unidad_reporte_N_2007_2008",
    "unidad_sumilla": "04_unidad_sumilla_2008_2009",
    "adjuntia_portada_estadistica": "05_adjuntia_portada_2009_2023",
    "infografia_ciclo_2024": "06_infografia_ciclo_2024_2026",
    "especial_no_mensual": "07_especial_no_mensual",
    "otro": "99_otro",
}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def leer_fechas() -> dict[str, dict]:
    rows = {}
    with FECHAS.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows[r["archivo"]] = r
    return rows


def caracterizar(path: Path) -> dict:
    doc = fitz.open(path)
    try:
        n_pag = doc.page_count
        p0 = doc[0]
        rect = p0.rect
        t0 = p0.get_text("text") or ""
        t1 = doc[1].get_text("text") if n_pag > 1 else ""
        texto = fold(t0 + "\n" + t1)
        texto = texto.replace("º", "o").replace("°", "o")
        n_img = len(p0.get_images(full=True))
        n_draw = len(p0.get_drawings())
        fonts = []
        d = p0.get_text("dict") or {}
        for b in d.get("blocks", []):
            for line in b.get("lines", []) or []:
                for sp in line.get("spans", []) or []:
                    fn = (sp.get("font") or "").split("+")[-1]
                    if fn:
                        fonts.append(fn)
        top_font = Counter(fonts).most_common(1)
        top_font = top_font[0][0] if top_font else ""
        chars = len(re.sub(r"\s+", "", t0))
        return {
            "paginas": n_pag,
            "ancho": round(rect.width),
            "alto": round(rect.height),
            "chars_p1": chars,
            "imgs_p1": n_img,
            "dibujos_p1": n_draw,
            "fuente_p1": top_font,
            "escaneado": chars < 250 and n_img >= 1,
            "texto_p1": re.sub(r"\s+", " ", t0).strip()[:500],
            "k_distinta_intensidad": "distinta intensidad" in texto,
            "k_reporte_n": bool(re.search(r"reporte\s+n[o.\s_-]*\s*\d+", texto[:2500])),
            "k_unidad": "unidad de conflictos" in texto[:3000],
            "k_direccion": "direccion de la unidad" in texto[:3000],
            "k_adjuntia": "adjuntia" in texto[:4000] or "subadjuntia" in texto[:4000],
            "k_sumilla": "sumilla" in texto[:2500],
            "k_especial": "reporte especial" in texto[:2000],
            "k_fase_ciclo": (
                "fase temprana" in texto[:4000] or "desescalamiento" in texto[:4000]
            ),
        }
    finally:
        doc.close()


def clasificar(c: dict, meta: dict, nombre: str) -> str:
    n = meta.get("numero")
    try:
        n = int(n) if n not in ("", None) else None
    except ValueError:
        n = None
    if "especial" in fold(nombre) or (c.get("k_especial") and c["paginas"] < 20):
        return "especial_no_mensual"
    if c["escaneado"] or (c["chars_p1"] < 80 and c["imgs_p1"] >= 1):
        return "escaneado_imagen"
    if c.get("k_fase_ciclo"):
        return "infografia_ciclo_2024"
    if c["k_adjuntia"]:
        return "adjuntia_portada_estadistica"
    if c["k_direccion"] or c["k_sumilla"]:
        return "unidad_sumilla"
    if c["k_unidad"] and c["k_reporte_n"]:
        return "unidad_reporte_n"
    if c["k_distinta_intensidad"] and not c["k_reporte_n"] and (n is None or n <= 3):
        return "lista_narrativa_2004"
    if c["k_reporte_n"]:
        return "reporte_n_tabla_regiones"
    if c["k_distinta_intensidad"]:
        return "lista_narrativa_2004"
    if n is not None and n <= 5:
        return "lista_narrativa_2004"
    return "otro"


def main() -> None:
    meta = leer_fechas()
    filas = []
    muestras = []
    for pdf in sorted(DEST.glob("*.pdf")):
        if fold(pdf.name).startswith("malnombrado"):
            continue
        m = meta.get(pdf.name, {})
        try:
            c = caracterizar(pdf)
        except Exception as exc:
            print("FAIL", pdf.name, exc)
            continue
        fmt = clasificar(c, m, pdf.name)
        fila = {
            "archivo": pdf.name,
            "numero": m.get("numero", ""),
            "mes": m.get("mes", ""),
            "anio": m.get("anio", ""),
            "formato": fmt,
            "paginas": c["paginas"],
            "ancho": c["ancho"],
            "alto": c["alto"],
            "chars_p1": c["chars_p1"],
            "imgs_p1": c["imgs_p1"],
            "dibujos_p1": c["dibujos_p1"],
            "fuente_p1": c["fuente_p1"],
            "escaneado": int(c["escaneado"]),
        }
        filas.append(fila)
        n = m.get("numero") or ""
        try:
            ni = int(n)
        except ValueError:
            ni = -1
        if ni in {1, 2, 5, 23, 33, 35, 50, 51, 61, 63, 79, 95, 191, 215, 238, 239, 266, 269} or fmt == "otro":
            muestras.append(
                f"=== n.{n} {m.get('anio')}-{m.get('mes')} [{fmt}] {pdf.name}\n"
                f"pag={c['paginas']} chars={c['chars_p1']} img={c['imgs_p1']} "
                f"font={c['fuente_p1']}\n{c['texto_p1'][:400]}\n"
            )
        print(f"{fmt:32} n={str(n):>4} p={c['paginas']:>3} {pdf.name[:70]}")

    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    MUESTRA.write_text("\n".join(muestras), encoding="utf-8")

    por_fmt = defaultdict(list)
    for f in filas:
        por_fmt[f["formato"]].append(f)

    GRUPOS.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for fmt, items in sorted(por_fmt.items(), key=lambda x: -len(x[1])):
        nums = sorted({int(i["numero"]) for i in items if str(i["numero"]).isdigit()})
        anios = sorted({int(i["anio"]) for i in items if str(i["anio"]).isdigit()})
        pags = [int(i["paginas"]) for i in items]
        resumen[fmt] = {
            "carpeta": CARPETAS.get(fmt, fmt),
            "n_pdf": len(items),
            "n_min": nums[0] if nums else None,
            "n_max": nums[-1] if nums else None,
            "anio_min": anios[0] if anios else None,
            "anio_max": anios[-1] if anios else None,
            "pag_mediana": sorted(pags)[len(pags) // 2] if pags else None,
            "numeros": nums,
            "archivos": [i["archivo"] for i in items],
        }
        carpeta = GRUPOS / CARPETAS.get(fmt, f"99_{fmt}")
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "ARCHIVOS.txt").write_text(
            "\n".join(i["archivo"] for i in items) + "\n", encoding="utf-8"
        )
        for i in items:
            src = DEST / i["archivo"]
            dst = carpeta / i["archivo"]
            if dst.exists() or not src.exists():
                continue
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        print(
            f"\n{fmt}: {len(items)} PDF | n.{resumen[fmt]['n_min']}-{resumen[fmt]['n_max']} | "
            f"{resumen[fmt]['anio_min']}-{resumen[fmt]['anio_max']} | ~{resumen[fmt]['pag_mediana']} pág"
        )

    OUT_JSON.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{OUT}")
    print(GRUPOS)


if __name__ == "__main__":
    main()
