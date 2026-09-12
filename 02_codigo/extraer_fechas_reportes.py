"""
Lee las primeras páginas de cada PDF (el formato de portada cambió con los años)
y arma el calendario mes/año cubierto vs huecos.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import fitz

from rutas import FECHAS_CSV, INVENTARIO, PDFS

CARPETA = PDFS
DRIVE_LIST = Path.home() / "AppData/Local/Temp/drive_defensoria_pdfs.txt"
SALIDA = INVENTARIO

MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
NOMBRE_MES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

RE_MES_ANIO = re.compile(
    r"\b("
    + "|".join(sorted(MESES.keys(), key=len, reverse=True))
    + r")\b[\s_\.\-]*(?:de(?:l)?[\s_\.\-]*)?(20\d{2})\b",
    re.IGNORECASE,
)
RE_NUMERO = re.compile(
    r"(?:reporte[^\n]{0,40})?n[°ºªo.\s_-]*\s*(\d{1,3})\b",
    re.IGNORECASE,
)
RE_AL = re.compile(
    r"al\s+(\d{1,2})\s+de\s+("
    + "|".join(MESES.keys())
    + r")\s+(?:del?\s+)?(20\d{2})",
    re.IGNORECASE,
)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def texto_portada(path: Path, paginas: int = 2) -> str:
    try:
        doc = fitz.open(path)
    except Exception:
        return ""
    partes = []
    try:
        n = min(paginas, doc.page_count)
        for i in range(n):
            partes.append(doc[i].get_text("text") or "")
    finally:
        doc.close()
    return "\n".join(partes)


RE_HEADER_NUM = re.compile(
    r"reporte(?:\s+mensual)?(?:\s+de)?\s+conflictos\s+sociales\s+"
    r"n[o.\s_-]*\s*(\d{1,3})\b",
    re.IGNORECASE,
)
RE_REPORTE_N = re.compile(r"reporte\s+n[o.\s_-]*\s*(\d{1,3})\b", re.IGNORECASE)
RE_NOMBRE_MES_ANIO = re.compile(
    r"^(?:mitad|final)\s+|"
    r"^(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre)\s+20\d{2}\b",
    re.IGNORECASE,
)


def extraer_de_texto(text: str) -> tuple[int | None, int | None, int | None]:
    """Devuelve (numero, mes, anio)."""
    t = fold(text)
    t = t.replace("º", "o").replace("°", "o")
    cabeza = t[:2500]
    numero = None
    mhead = RE_HEADER_NUM.search(cabeza) or RE_REPORTE_N.search(cabeza[:1500])
    if not mhead:
        mhead = re.search(
            r"conflictos\s+sociales\s+n[o.\s_-]*\s*(\d{1,3})\b", cabeza
        ) or RE_NUMERO.search(cabeza)
    if mhead:
        n = int(mhead.group(1))
        if 1 <= n <= 320:
            numero = n

    mes = anio = None
    # Mes/año pegado al encabezado (formato actual: "N.° 252 / Febrero 2025")
    if mhead:
        after = t[mhead.end() : mhead.end() + 500]
        mh = RE_MES_ANIO.search(after)
        if mh:
            return numero, MESES[mh.group(1).lower()], int(mh.group(2))

    # "al 30 de abril de 2009" es el cierre del mes reportado
    mal = RE_AL.search(t[:4000])
    if mal:
        mes = MESES[mal.group(2).lower()]
        anio = int(mal.group(3))
        return numero, mes, anio

    hits = list(RE_MES_ANIO.finditer(cabeza))
    if hits:
        elegido = hits[0]
        for h in hits:
            start = max(0, h.start() - 80)
            ctx = cabeza[start : h.end() + 20]
            if "conflicto" in ctx or "reporte" in ctx:
                elegido = h
                break
        mes = MESES[elegido.group(1).lower()]
        anio = int(elegido.group(2))
    return numero, mes, anio


def extraer_de_nombre(name: str) -> tuple[int | None, int | None, int | None]:
    t = fold(Path(name).stem)
    t = t.replace("º", "o").replace("°", "o")
    numero = None
    mnum = re.search(r"n[o.\s_-]*\s*(\d{1,3})\b", t) or re.search(
        r"conflictos(?:[_\s-]*sociales)?[_\s-]*(\d{1,3})\b", t
    )
    if mnum:
        n = int(mnum.group(1))
        if 1 <= n <= 320:
            numero = n
            if n < 50:
                # conflictos_sociales42.pdf → número 42
                pass
    mes = anio = None
    hits = list(RE_MES_ANIO.finditer(t))
    if hits:
        mes = MESES[hits[-1].group(1).lower()]
        anio = int(hits[-1].group(2))
    # "Mar_2025", "Abr_2025", "febrero-26"
    if mes is None:
        m = re.search(
            r"(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*[_\s\-\.]*(20)?(\d{2})\b",
            t,
        )
        if m:
            mes = MESES.get(m.group(1))
            yy = m.group(3)
            anio = int("20" + yy) if len(yy) == 2 else int(yy)
            if anio < 2000:
                anio += 2000
    # "abril 2004 - Reporte 01"
    if numero is None:
        mrep = re.search(r"reporte\s*0*(\d{1,2})\b", t)
        if mrep and mes and anio and anio <= 2005:
            numero = int(mrep.group(1))
    return numero, mes, anio


def leer_drive() -> list[dict]:
    rows = []
    if not DRIVE_LIST.exists():
        return rows
    for line in DRIVE_LIST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name = line.split("\t")[0].split("/")[-1]
        n, mes, anio = extraer_de_nombre(name)
        rows.append({"archivo": name, "origen": "drive", "numero": n, "mes": mes, "anio": anio})
    return rows


def leer_locales() -> list[dict]:
    rows = []
    for pdf in sorted(CARPETA.glob("*.pdf")):
        n_nom, mes_nom, anio_nom = extraer_de_nombre(pdf.name)
        text = texto_portada(pdf)
        n_txt, mes_txt, anio_txt = extraer_de_texto(text) if text.strip() else (None, None, None)
        rows.append(
            {
                "archivo": pdf.name,
                "origen": "nuevo",
                "numero": n_txt or n_nom,
                "mes": mes_txt or mes_nom,
                "anio": anio_txt or anio_nom,
                "fuente_fecha": "pdf" if (mes_txt and anio_txt) else ("nombre" if mes_nom else "sin_fecha"),
                "chars_portada": len(text.strip()),
            }
        )
    return rows


def main() -> None:
    locales = leer_locales()
    drive = leer_drive()

    # Calendario: (anio, mes) -> fuentes
    cal: dict[tuple[int, int], dict] = defaultdict(lambda: {"nuevo": [], "drive": [], "numeros": set()})

    for r in locales:
        if r["anio"] and r["mes"]:
            key = (r["anio"], r["mes"])
            cal[key]["nuevo"].append(r["archivo"])
            if r["numero"]:
                cal[key]["numeros"].add(r["numero"])
    for r in drive:
        if r["anio"] and r["mes"]:
            key = (r["anio"], r["mes"])
            cal[key]["drive"].append(r["archivo"])
            if r["numero"]:
                cal[key]["numeros"].add(r["numero"])

    # Serie esperada: abril 2004 → julio 2026 (último publicado n.269)
    inicio = (2004, 4)
    fin = (2026, 7)

    def iter_meses(a0, m0, a1, m1):
        y, m = a0, m0
        while (y, m) <= (a1, m1):
            yield y, m
            m += 1
            if m == 13:
                m = 1
                y += 1

    lineas = []
    lineas.append("AÑO  ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC")
    huecos = []
    cubiertos = []
    for year in range(inicio[0], fin[0] + 1):
        celdas = [f"{year}"]
        for month in range(1, 13):
            if (year, month) < inicio or (year, month) > fin:
                celdas.append("   ")
                continue
            info = cal.get((year, month))
            if not info:
                celdas.append(" · ")
                huecos.append((year, month))
            else:
                marca = "DN" if info["nuevo"] and info["drive"] else (" N" if info["nuevo"] else " D")
                celdas.append(marca)
                cubiertos.append((year, month, sorted(info["numeros"]), marca.strip()))
        lineas.append(" ".join(f"{c:>3}" for c in celdas))

    reporte = SALIDA / "calendario_reportes_defensoria.txt"
    csv_path = SALIDA / "calendario_reportes_defensoria.csv"
    detalle = SALIDA / "fechas_extraidas_pdfs.csv"

    with detalle.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["origen", "archivo", "numero", "mes", "anio", "fuente_fecha", "chars_portada"],
        )
        w.writeheader()
        for r in locales:
            w.writerow(
                {
                    "origen": r["origen"],
                    "archivo": r["archivo"],
                    "numero": r["numero"] or "",
                    "mes": r["mes"] or "",
                    "anio": r["anio"] or "",
                    "fuente_fecha": r.get("fuente_fecha", ""),
                    "chars_portada": r.get("chars_portada", ""),
                }
            )
        for r in drive:
            w.writerow(
                {
                    "origen": r["origen"],
                    "archivo": r["archivo"],
                    "numero": r["numero"] or "",
                    "mes": r["mes"] or "",
                    "anio": r["anio"] or "",
                    "fuente_fecha": "nombre",
                    "chars_portada": "",
                }
            )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["anio", "mes", "mes_nombre", "en_drive", "en_nuevo", "numeros", "estado"])
        for y, m in iter_meses(*inicio, *fin):
            info = cal.get((y, m), {"nuevo": [], "drive": [], "numeros": set()})
            en_d = bool(info["drive"])
            en_n = bool(info["nuevo"])
            if en_d and en_n:
                estado = "ambos"
            elif en_d:
                estado = "solo_drive"
            elif en_n:
                estado = "solo_nuevo"
            else:
                estado = "falta"
            w.writerow(
                [
                    y,
                    m,
                    NOMBRE_MES[m],
                    en_d,
                    en_n,
                    " ".join(str(n) for n in sorted(info["numeros"])),
                    estado,
                ]
            )

    n_pdf_ok = sum(1 for r in locales if r.get("fuente_fecha") == "pdf")
    n_pdf_nom = sum(1 for r in locales if r.get("fuente_fecha") == "nombre")
    n_pdf_no = sum(1 for r in locales if r.get("fuente_fecha") == "sin_fecha")

    cuerpo = []
    cuerpo.append("Calendario de reportes mensuales de conflictos sociales")
    cuerpo.append("Periodo esperado: abril 2004 — julio 2026 (último publicado n.º 269).")
    cuerpo.append("Marca: D = solo Drive | N = solo descarga nueva | DN = en los dos | · = falta")
    cuerpo.append("")
    cuerpo.extend(lineas)
    cuerpo.append("")
    cuerpo.append(f"Meses cubiertos: {len(cubiertos)}")
    cuerpo.append(f"Meses faltantes: {len(huecos)}")
    cuerpo.append("")
    cuerpo.append("Faltan:")
    if not huecos:
        cuerpo.append("  (ninguno en el rango)")
    else:
        por_anio = defaultdict(list)
        for y, m in huecos:
            por_anio[y].append(NOMBRE_MES[m])
        for y in sorted(por_anio):
            cuerpo.append(f"  {y}: " + ", ".join(por_anio[y]))
    cuerpo.append("")
    cuerpo.append("Lectura dentro del PDF (descarga nueva):")
    cuerpo.append(f"  fecha leída de la portada: {n_pdf_ok}")
    cuerpo.append(f"  solo del nombre de archivo: {n_pdf_nom}")
    cuerpo.append(f"  sin fecha: {n_pdf_no}")
    cuerpo.append("")
    cuerpo.append("Los de Drive sin PDF local se fecharon por el nombre del archivo.")

    reporte.write_text("\n".join(cuerpo) + "\n", encoding="utf-8")

    # Lo que usa clasificar_formatos_pdf.py / extraer_conflictos.py.
    # Solo PDF locales: no hace falta la lista de Drive.
    with FECHAS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["archivo", "numero", "mes", "anio", "fuente_fecha"]
        )
        w.writeheader()
        for r in locales:
            w.writerow(
                {
                    "archivo": r["archivo"],
                    "numero": r["numero"] or "",
                    "mes": r["mes"] or "",
                    "anio": r["anio"] or "",
                    "fuente_fecha": r.get("fuente_fecha") or "",
                }
            )

    print("\n".join(cuerpo))
    print(f"\nEscrito: {reporte}")
    print(csv_path)
    print(detalle)
    print(FECHAS_CSV)


if __name__ == "__main__":
    main()
