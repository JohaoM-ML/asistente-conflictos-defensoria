"""
Une PDF de la descarga local + los que solo están en Drive Minería
en una sola carpeta, y arma el consolidado de huecos.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extraer_fechas_reportes as fechas
from rutas import DESCARGA_PARCIAL, FECHAS_CSV, INVENTARIO, INVENTARIO_CSV, PDFS

LOCAL = DESCARGA_PARCIAL
DESTINO = PDFS
DRIVE_LIST = Path.home() / "AppData/Local/Temp/drive_defensoria_pdfs.txt"
TOKENS = Path.home() / ".config/google-workspace-mcp/tokens.json"
MCP = Path.home() / ".cursor/mcp.json"
NOMBRE_MES = fechas.NOMBRE_MES


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def es_reporte_mensual(name: str) -> bool:
    t = fold(name)
    if "adjuntia" in t or "costos-del-conflicto" in t or "costos_del_conflicto" in t:
        return False
    return True


def clave(name: str) -> str:
    s = fold(Path(name).stem)
    s = re.sub(r"reporte[-_ ]*(mensual[-_ ]*de[-_ ]*)?conflictos[-_ ]*sociales[-_ ]*", "", s)
    s = re.sub(r"n[o.\s_-]*", "n", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def numero(name: str) -> int | None:
    if not es_reporte_mensual(name):
        return None
    t = fold(Path(name).stem)
    if t.startswith("malnombrado"):
        return None
    # Prefijo n69_ de inventario viejo no es el número de reporte si hay otro n.º.
    t_sin_inv = re.sub(r"^n\d{1,3}_", "", t)
    ms = list(re.finditer(r"(?:^|[-_\s])n[o.\s_-]*(\d{1,3})(?!\d)", t_sin_inv))
    if ms:
        n = int(ms[-1].group(1))
        if 1 <= n <= 320:
            return n
    m = re.search(r"conflictos(?:[_\s-]*sociales)?[_\s-]*(\d{1,3})\b", t_sin_inv)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 320:
            return n
    m = re.search(r"reporte[-_\s]*(\d{1,3})\b", t_sin_inv)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 269:
            return n
    return None


def fecha_de_pdf(pdf: Path) -> tuple[int | None, int | None, int | None, str]:
    """(numero, mes, anio, fuente). Prefiere el nombre si es 'abril 2004 - ...'."""
    n_nom, mes_nom, anio_nom = fechas.extraer_de_nombre(pdf.name)
    text = fechas.texto_portada(pdf)
    n_txt, mes_txt, anio_txt = (
        fechas.extraer_de_texto(text) if text.strip() else (None, None, None)
    )
    stem = fold(pdf.stem)
    if fechas.RE_NOMBRE_MES_ANIO.search(stem) and mes_nom and anio_nom:
        return n_nom or n_txt, mes_nom, anio_nom, "nombre"
    n = n_txt or n_nom
    mes = mes_txt or mes_nom
    anio = anio_txt or anio_nom
    fuente = "pdf" if (mes_txt and anio_txt) else ("nombre" if mes_nom else "sin_fecha")
    return n, mes, anio, fuente


def nombre_seguro(name: str) -> str:
    name = Path(name).name
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.replace("\u00b0", "o").replace("\u00ba", "o")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def poner(src: Path, dst_dir: Path, nombre: str) -> Path:
    dest = dst_dir / nombre_seguro(nombre)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)
    return dest


def token_drive() -> str:
    tok = json.loads(TOKENS.read_text(encoding="utf-8"))
    mcp = json.loads(MCP.read_text(encoding="utf-8"))
    env = mcp["mcpServers"]["google-drive"]["env"]
    body = urllib.parse.urlencode(
        {
            "client_id": env["GOOGLE_CLIENT_ID"],
            "client_secret": env["GOOGLE_CLIENT_SECRET"],
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data["access_token"]


def bajar_drive(file_id: str, dest: Path, access: str) -> None:
    url = (
        "https://www.googleapis.com/drive/v3/files/"
        + urllib.parse.quote(file_id)
        + "?alt=media&supportsAllDrives=true"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def armar_inventario_fechas() -> None:
    filas = []
    cal: dict[tuple[int, int], list[str]] = defaultdict(list)
    notas = []
    for pdf in sorted(DESTINO.glob("*.pdf")):
        if fold(pdf.name).startswith("malnombrado"):
            notas.append(
                f"  {pdf.name} — mal nombrado (el PDF no es el n.º del nombre); no cuenta en el calendario."
            )
            continue
        n, mes, anio, fuente_fecha = fecha_de_pdf(pdf)
        if "especial" in fold(pdf.name):
            notas.append(f"  {pdf.name} — reporte especial, no es el mensual de ese mes.")
        filas.append(
            {
                "archivo": pdf.name,
                "numero": n or "",
                "mes": mes or "",
                "anio": anio or "",
                "fuente_fecha": fuente_fecha,
            }
        )
        if anio and mes and "especial" not in fold(pdf.name):
            cal[(anio, mes)].append(pdf.name)

    det_path = FECHAS_CSV
    with det_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["archivo", "numero", "mes", "anio", "fuente_fecha"])
        w.writeheader()
        w.writerows(filas)

    inicio, fin = (2004, 4), (2026, 7)
    huecos = []
    cubiertos = []
    lineas = ["AÑO  ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC"]
    for year in range(2004, 2027):
        celdas = [f"{year}"]
        for month in range(1, 13):
            if (year, month) < inicio or (year, month) > fin:
                celdas.append("   ")
                continue
            if (year, month) in cal:
                celdas.append("  X")
                cubiertos.append((year, month))
            else:
                celdas.append("  ·")
                huecos.append((year, month))
        lineas.append(" ".join(f"{c:>3}" for c in celdas))

    por_anio: dict[int, list[str]] = defaultdict(list)
    for y, m in huecos:
        por_anio[y].append(NOMBRE_MES[m])

    nums = sorted(
        {
            int(f["numero"])
            for f in filas
            if str(f["numero"]).isdigit() and "especial" not in fold(f["archivo"])
        }
    )
    huecos_n = [i for i in range(1, 270) if i not in set(nums)] if nums else []

    cuerpo = []
    cuerpo.append("CONSOLIDADO — reportes mensuales Defensoría del Pueblo")
    cuerpo.append(f"Carpeta: {DESTINO}")
    cuerpo.append(f"PDF en la carpeta: {len(list(DESTINO.glob('*.pdf')))}")
    cuerpo.append("Unión de: descarga web + lo que había en Drive y no estaba local.")
    cuerpo.append("Periodo esperado: abril 2004 — julio 2026 (n.º 269).")
    cuerpo.append("X = hay PDF    · = falta")
    cuerpo.append("")
    cuerpo.extend(lineas)
    cuerpo.append("")
    cuerpo.append(f"Meses cubiertos: {len(cubiertos)}")
    cuerpo.append(f"Meses faltantes: {len(huecos)}")
    cuerpo.append("")
    cuerpo.append("Faltan (mes/año):")
    if not huecos:
        cuerpo.append("  (ninguno)")
    else:
        for y in sorted(por_anio):
            cuerpo.append(f"  {y}: " + ", ".join(por_anio[y]))
    cuerpo.append("")
    cuerpo.append(
        f"Números de reporte presentes: {len(nums)} "
        f"(min {nums[0] if nums else '-'} / max {nums[-1] if nums else '-'})"
    )
    cuerpo.append(f"Números 1–269 que no aparecen: {len(huecos_n)}")
    if huecos_n:
        cuerpo.append("  " + ", ".join(str(n) for n in huecos_n))
    if notas:
        cuerpo.append("")
        cuerpo.append("Notas:")
        cuerpo.extend(notas)

    cons = INVENTARIO / "CONSOLIDADO.txt"
    cons.write_text("\n".join(cuerpo) + "\n", encoding="utf-8")
    cons2 = INVENTARIO / "CONSOLIDADO_defensoria.txt"
    cons2.write_text("\n".join(cuerpo) + "\n", encoding="utf-8")
    print("\n".join(cuerpo))
    print(f"\n{cons}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solo-fechas", action="store_true")
    args = parser.parse_args()
    DESTINO.mkdir(parents=True, exist_ok=True)
    if args.solo_fechas:
        armar_inventario_fechas()
        return

    inventario = []

    locales = [p for p in LOCAL.glob("*.pdf") if es_reporte_mensual(p.name)]
    by_clave: dict[str, str] = {}
    by_num: dict[int, str] = {}
    for p in locales:
        dest = poner(p, DESTINO, p.name)
        inventario.append({"archivo": dest.name, "fuente": "local", "id_drive": ""})
        by_clave[clave(p.name)] = dest.name
        n = numero(p.name)
        if n is not None:
            by_num[n] = dest.name
    print(f"Copiados desde local: {len(locales)}")

    drive_rows = []
    for line in DRIVE_LIST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0].split("/")[-1]
        fid = parts[3] if len(parts) > 3 else ""
        drive_rows.append((name, fid))

    access = token_drive()
    bajados = 0
    ya = 0
    fail = 0
    for name, fid in drive_rows:
        c = clave(name)
        n = numero(name)
        if c in by_clave or (n is not None and n in by_num):
            ya += 1
            continue
        dest = DESTINO / nombre_seguro(name)
        if dest.exists() and dest.stat().st_size > 1000:
            ya += 1
            inventario.append({"archivo": dest.name, "fuente": "drive", "id_drive": fid})
            continue
        try:
            bajar_drive(fid, dest, access)
            if dest.stat().st_size < 500:
                dest.unlink(missing_ok=True)
                raise RuntimeError("archivo demasiado chico")
            inventario.append({"archivo": dest.name, "fuente": "drive", "id_drive": fid})
            by_clave[c] = dest.name
            if n is not None:
                by_num[n] = dest.name
            bajados += 1
            print(f"  Drive + {dest.name}")
            time.sleep(0.35)
        except Exception as exc:
            fail += 1
            print(f"  FAIL {name} :: {exc}")

    print(f"Desde Drive nuevos: {bajados}  ya cubiertos: {ya}  fallos: {fail}")
    print(f"Total en carpeta: {len(list(DESTINO.glob('*.pdf')))}")

    inv_path = INVENTARIO_CSV
    with inv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["archivo", "fuente", "id_drive"])
        w.writeheader()
        w.writerows(inventario)

    armar_inventario_fechas()


if __name__ == "__main__":
    main()
