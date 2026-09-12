"""
Extrae fichas de conflictos de los PDF mensuales de la Defensoría.

Uso:
    python -u 02_codigo/extraer_conflictos.py
    python -u 02_codigo/extraer_conflictos.py --max 5
    python -u 02_codigo/extraer_conflictos.py --solo-numero 169
    python -u 02_codigo/extraer_conflictos.py --identidad fuzzy
"""
from __future__ import annotations

import argparse
import csv
import gzip
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from defensoria_extract.fichas import ExtractorPaginas, fichas_tabla_latentes, fichas_texto_corrido
from defensoria_extract.flags import completar_departamento, flags
from defensoria_extract import identidad_emb
from defensoria_extract.identidad import agrupar
from defensoria_extract.layout import abrir, bloques_pagina, fold, texto_pagina_simple
from defensoria_extract.secciones import pagina_es_latentes, pagina_es_stop, pagina_inicia_detalle
from rutas import ENCODING_CSV, FORMATOS_CSV as FORMATOS
from rutas import PDFS
from rutas import PROCESADOS as SALIDA

CAMPOS_SALIDA = [
    "caso_id",
    "numero_reporte",
    "anio",
    "mes",
    "estado",
    "departamento",
    "tipo",
    "caso",
    "ubicacion",
    "actores_primarios",
    "actores_secundarios",
    "actores_terciarios",
    "actores",
    "ingreso_como",
    "codigo",
    "hechos_del_mes",
    "es_socioambiental",
    "menciona_mineria",
    "formato",
    "archivo",
    "pagina",
    "caso_estandarizado",
    "texto_crudo",
]


def detectar_estado(raw: str, actual: str | None) -> str | None:
    # Latentes puede aparecer tarde en la página (tras el cierre de un activo).
    t_full = fold(raw or "")
    if "detalle de los conflictos latentes" in t_full:
        return "Latente"
    t = fold(raw[:2200])
    if "detalle de los conflictos sociales activos" in t:
        return "Activo"
    if "activos desarrollados en un solo departamento" in t:
        return "Activo"
    if "desarrollados en mas de un departamento" in t:
        return "Activo"
    if "casos fusionados" in t[:600] or "conflictos fusionados" in t[:600]:
        return "Fusionado"
    if "casos en observacion" in t_full[:2500]:
        return "Inactivo"
    if "conflictos reactivados" in t[:900]:
        return "Reactivado"
    if "conflictos resueltos" in t[:900] and "cuadro" not in t[:200]:
        return "Resuelto"
    if "conflictos concluidos" in t[:600]:
        return "Resuelto"
    if "nuevos casos" in t[:400]:
        return "Nuevo"
    if "conflictos vigentes" in t[:500]:
        return "Activo"
    return actual


CORRIDO_FMT = {
    "lista_narrativa_2004",
    "reporte_n_tabla_regiones",
    "unidad_reporte_n",
}


def modo_columnas(doc, fmt: str = "") -> bool:
    if fmt in CORRIDO_FMT:
        return False
    if fmt in {
        "unidad_sumilla",
        "adjuntia_portada_estadistica",
        "infografia_ciclo_2024",
    }:
        return True
    ntipo = 0
    for i in range(min(doc.page_count, 55)):
        ntipo += len(re.findall(r"tipo\s*:", fold(texto_pagina_simple(doc[i]))))
        if ntipo >= 8:
            return True
    return ntipo >= 8


def cargar_inventario() -> list[dict]:
    filas = []
    with FORMATOS.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("formato") == "especial_no_mensual":
                continue
            if (r.get("archivo") or "").startswith("MALNOMBRADO"):
                continue
            filas.append(r)
    por: dict[str, dict] = {}
    sin = []
    for r in filas:
        n = r.get("numero") or ""
        if not n:
            sin.append(r)
            continue
        prev = por.get(n)
        existe = (PDFS / (r.get("archivo") or "")).exists()
        prev_existe = (
            prev is not None and (PDFS / (prev.get("archivo") or "")).exists()
        )
        if prev is None:
            por[n] = r
            continue
        # Preferir un archivo que exista en disco; entre existentes, el de más páginas.
        if existe and not prev_existe:
            por[n] = r
        elif existe == prev_existe:
            if int(r.get("paginas") or 0) > int(prev.get("paginas") or 0):
                por[n] = r
    out = list(por.values()) + sin
    out.sort(key=lambda x: (int(x["anio"] or 0), int(x["mes"] or 0), x["archivo"]))
    return out


def _es_basura(f: dict) -> bool:
    caso = (f.get("caso") or "").strip()
    c = fold(caso)
    if c.startswith(
        (
            "y fecha de inicio",
            "ultimos acontecimientos",
            "ubicacion autoridad",
            "motivo y fecha",
        )
    ):
        return True
    if not caso and not f.get("tipo") and not f.get("codigo"):
        return True
    # Un caso de una o dos palabras sueltas no describe nada; si además no trae
    # tipo ni ubicación, es un resto de maquetación, no una ficha.
    if caso and len(caso.split()) < 4 and not f.get("tipo") and not f.get("ubicacion"):
        return True
    return False


def extraer_pdf(meta: dict) -> tuple[list[dict], list[dict]]:
    path = PDFS / meta["archivo"]
    if not path.exists():
        return [], [{"archivo": meta["archivo"], "motivo": "no existe"}]
    try:
        doc = abrir(path)
    except Exception as exc:
        return [], [{"archivo": meta["archivo"], "motivo": str(exc)}]

    fmt = meta.get("formato") or ""
    ya = False
    estado: str | None = None
    filas: list[dict] = []
    try:
        columnas = modo_columnas(doc, fmt)
        ext = ExtractorPaginas()
        dept = ""
        corrido_txt: list[str] = []
        latentes_txt: list[str] = []
        en_latentes = False
        latentes_pagina = 0
        for i, page in enumerate(doc):
            raw = texto_pagina_simple(page)
            if not ya:
                if pagina_inicia_detalle(raw):
                    ya = True
                    estado = "Activo"
                    ext.estado = "Activo"
                else:
                    continue
            if pagina_es_stop(raw, ya):
                break
            estado = detectar_estado(raw, estado) or estado or "Activo"
            ext.estado = estado
            if pagina_es_latentes(raw) or estado == "Latente":
                en_latentes = True
            if en_latentes:
                if not latentes_pagina:
                    latentes_pagina = i + 1
                # Si la página ya abre la sección siguiente, conservar solo el tramo previo.
                mcut = re.search(
                    r"(?i)(?:^|\n)\s*(?:viii\.?\s*|ix\.?\s*|x\.?\s*)?(?:"
                    r"casos en observaci[oó]n|"
                    r"conflictos(?:\s+\w+){0,4}\s+resueltos|"
                    r"conflictos que han pasado|"
                    r"forma de resoluci[oó]n|"
                    r"acciones colectivas de protesta|"
                    r"hechos de violencia|"
                    r"actuaciones defensoriales"
                    r")",
                    raw,
                )
                if mcut and mcut.start() > 80:
                    latentes_txt.append(raw[: mcut.start()])
                    en_latentes = False
                    # Evitar que el extractor de columnas siga etiquetando Latente.
                    estado = "Inactivo"
                    ext.estado = "Inactivo"
                elif mcut:
                    en_latentes = False
                    estado = "Inactivo"
                    ext.estado = "Inactivo"
                else:
                    latentes_txt.append(raw)
            if columnas:
                ext.feed(bloques_pagina(page, i + 1))
            else:
                corrido_txt.append(raw)
        if columnas:
            filas = ext.finish()
        else:
            filas, _ = fichas_texto_corrido("\n".join(corrido_txt), "Activo", "")
        if latentes_txt:
            extras = fichas_tabla_latentes(
                "\n".join(latentes_txt), pagina=latentes_pagina or 0
            )
            # Evitar duplicar si el extractor de columnas ya sacó alguna latente con Tipo:
            ya_casos = {
                fold((f.get("caso") or "")[:80]) for f in filas if f.get("estado") == "Latente"
            }
            for f in extras:
                clave = fold((f.get("caso") or "")[:80])
                if clave and clave in ya_casos:
                    continue
                filas.append(f)
                if clave:
                    ya_casos.add(clave)
    finally:
        doc.close()

    out = []
    for f in filas:
        if _es_basura(f):
            continue
        f["archivo"] = meta["archivo"]
        f["numero_reporte"] = meta.get("numero") or ""
        f["anio"] = meta.get("anio") or ""
        f["mes"] = meta.get("mes") or ""
        f["formato"] = fmt
        f.update(flags(f))
        completar_departamento(f)
        out.append(f)
    fallos = []
    if not out:
        fallos.append({"archivo": meta["archivo"], "motivo": "cero fichas"})
    return out, fallos


def escribir(filas: list[dict], fallos: list[dict], resumen: str) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    panel = SALIDA / "panel_caso_mes.csv"
    with panel.open("w", encoding=ENCODING_CSV, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS_SALIDA, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    unicos: dict = {}
    meses_por: dict = {}
    for f in filas:
        cid = f.get("caso_id")
        if cid not in unicos:
            unicos[cid] = {
                "caso_id": cid,
                "caso": f.get("caso"),
                "departamento": f.get("departamento"),
                "tipo": f.get("tipo"),
                "n_meses": 0,
                "n_apariciones": 0,
                "es_socioambiental": f.get("es_socioambiental"),
                "menciona_mineria": f.get("menciona_mineria"),
            }
            meses_por[cid] = set()
        unicos[cid]["n_apariciones"] += 1
        am = (str(f.get("anio") or ""), str(f.get("mes") or ""))
        if am[0] or am[1]:
            meses_por[cid].add(am)
        unicos[cid]["menciona_mineria"] = int(
            bool(unicos[cid]["menciona_mineria"] or f.get("menciona_mineria"))
        )
        unicos[cid]["es_socioambiental"] = int(
            bool(unicos[cid]["es_socioambiental"] or f.get("es_socioambiental"))
        )
    for cid, u in unicos.items():
        u["n_meses"] = len(meses_por.get(cid) or [])
    with (SALIDA / "casos_unicos.csv").open("w", encoding=ENCODING_CSV, newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "caso_id",
                "caso",
                "departamento",
                "tipo",
                "n_meses",
                "n_apariciones",
                "es_socioambiental",
                "menciona_mineria",
            ],
        )
        w.writeheader()
        w.writerows(unicos.values())

    with (SALIDA / "fallos.csv").open("w", encoding=ENCODING_CSV, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["archivo", "motivo"])
        w.writeheader()
        w.writerows(fallos)
    (SALIDA / "RESUMEN.txt").write_text(resumen, encoding="utf-8")
    gz = SALIDA / "panel_caso_mes.csv.gz"
    with panel.open("rb") as src, gzip.open(gz, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    print(resumen)
    print(panel)
    print(gz)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=0)
    parser.add_argument("--solo-numero", type=str, default="")
    parser.add_argument("--sin-fuzzy", action="store_true")
    parser.add_argument(
        "--identidad",
        choices=["embeddings", "fuzzy"],
        default="embeddings",
        help="cómo agrupar filas en casos (ver comparar_identidad.py)",
    )
    parser.add_argument("--umbral", type=float, default=None)
    args = parser.parse_args()

    if not FORMATOS.exists():
        raise SystemExit(
            f"Falta {FORMATOS}. En un clon, o bien usas el inventario del repo, "
            "o regeneras: python -u 02_codigo/extraer_fechas_reportes.py "
            "y luego python -u 02_codigo/clasificar_formatos_pdf.py"
        )
    n_pdf = len(list(PDFS.glob("*.pdf"))) if PDFS.exists() else 0
    if n_pdf == 0:
        raise SystemExit(
            f"No hay PDF en {PDFS}. "
            "Bájalos con: python -u 02_codigo/descargar_reportes_defensoria.py "
            "o copia el corpus a esa carpeta. "
            "Para solo analizar el panel ya extraído, no hace falta este script: "
            "usa 01_datos/procesados/conflictos/panel_caso_mes.csv.gz"
        )

    inventario = cargar_inventario()
    if args.solo_numero:
        inventario = [r for r in inventario if r.get("numero") == args.solo_numero]
    if args.max:
        inventario = inventario[: args.max]

    todas: list[dict] = []
    fallos: list[dict] = []
    por_fmt: Counter[str] = Counter()
    por_n: list[str] = []
    for i, meta in enumerate(inventario, 1):
        try:
            filas, f = extraer_pdf(meta)
        except Exception as exc:
            filas, f = [], [{"archivo": meta["archivo"], "motivo": f"error: {exc}"}]
        todas.extend(filas)
        fallos.extend(f)
        por_fmt[meta.get("formato") or "?"] += len(filas)
        ncaso = sum(1 for x in filas if x.get("caso"))
        por_n.append(
            f"n.{meta.get('numero')}: {len(filas)} fichas ({ncaso} con caso) {meta['archivo'][:55]}"
        )
        print(
            f"[{i}/{len(inventario)}] n.{meta.get('numero')} "
            f"{len(filas):4} fichas  {meta['archivo'][:70]}",
            flush=True,
        )

    metodo_id = "ninguno"
    if not args.sin_fuzzy:
        metodo_id = args.identidad
        if args.identidad == "embeddings":
            umbral = args.umbral or identidad_emb.UMBRAL_DEFECTO
            print(
                f"Agrupando identidades (embeddings, umbral {umbral}, "
                "bloqueado por departamento)...",
                flush=True,
            )
            identidad_emb.agrupar(todas, umbral=umbral)
            metodo_id = f"embeddings (umbral {umbral})"
        else:
            print("Agrupando identidades (fuzzy por departamento)...", flush=True)
            agrupar(todas, umbral=args.umbral or 88.0)
            metodo_id = f"fuzzy (umbral {args.umbral or 88.0})"

    n_con_caso = sum(1 for f in todas if f.get("caso"))
    n_mineria = sum(1 for f in todas if f.get("menciona_mineria"))
    n_socio = sum(1 for f in todas if f.get("es_socioambiental"))
    ids = {f.get("caso_id") for f in todas if f.get("caso_id") is not None}
    lineas = [
        "EXTRACCIÓN DE CONFLICTOS — Defensoría del Pueblo",
        f"PDF procesados: {len(inventario)}",
        f"Filas (caso × mes): {len(todas)}",
        f"Con campo caso: {n_con_caso}",
        f"Casos únicos: {len(ids)}",
        f"Método de identidad: {metodo_id}",
        f"Socioambientales: {n_socio}",
        f"Mencionan minería: {n_mineria}",
        f"PDF sin fichas: {len(fallos)}",
        "",
        "Fichas por formato:",
    ]
    for k, v in por_fmt.most_common():
        lineas.append(f"  {k}: {v}")
    lineas.append("")
    lineas.append("Notas:")
    lineas.append(
        "- Fichas con Tipo/Caso/Ubicación (o Motivo/Actores en 2004–2007)."
    )
    lineas.append(
        "- Latentes en tablas compactas (Adjuntía 2009+ / infografía 2024+) se"
    )
    lineas.append(
        "  recuperan del detalle tabular; antes de este arreglo se perdían desde ~2009."
    )
    lineas.append(
        "- Desde el reporte ~248 el detalle de ACTIVOS solo incluye los que"
    )
    lineas.append(
        "  'registraron hechos durante el mes'; el resto de activos del mes no"
    )
    lineas.append(
        "  tienen ficha completa en el PDF (cambio de la Defensoría, no del extractor)."
    )
    lineas.append(
        "- Minería: filtrar es_socioambiental=1 y/o menciona_mineria=1; no se borró el resto."
    )
    lineas.append(
        "- n_meses = meses únicos (anio, mes); n_apariciones = filas del panel."
    )
    lineas.append("")
    lineas.append("Por reporte:")
    lineas.extend(por_n)
    if fallos:
        lineas.append("")
        lineas.append("Fallos:")
        for x in fallos[:80]:
            lineas.append(f"  {x['archivo']}: {x['motivo']}")
        no_existe = [x for x in fallos if "no existe" in (x.get("motivo") or "")]
        if no_existe:
            print(
                f"AVISO: {len(no_existe)} PDF del inventario no existen en disco "
                f"(revisar formatos_pdf_defensoria.csv):",
                flush=True,
            )
            for x in no_existe[:20]:
                print(f"  - {x['archivo']}", flush=True)
    escribir(todas, fallos, "\n".join(lineas) + "\n")


if __name__ == "__main__":
    main()
