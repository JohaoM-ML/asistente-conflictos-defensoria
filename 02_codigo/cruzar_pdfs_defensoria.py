"""Cruza PDF locales (descarga nueva) vs PDF ya en Drive Minería/defensoria_pdfs."""
from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from rutas import DESCARGA_PARCIAL, INVENTARIO

DRIVE_LIST = Path.home() / "AppData/Local/Temp/drive_defensoria_pdfs.txt"
LOCAL_DIR = DESCARGA_PARCIAL
OUT = INVENTARIO / "cruce_defensoria_drive_vs_nuevos.csv"

RE_N = re.compile(
    r"(?:n[°ºªo.\s_-]*|numero\s*)(\d{1,3})(?!\d)",
    re.IGNORECASE,
)
RE_CONFLICTOS_N = re.compile(
    r"conflictos(?:[_\s-]*sociales)?[_\s-]*(\d{1,3})(?!\d)",
    re.IGNORECASE,
)
RE_YEAR = re.compile(r"^(19|20)\d{2}$")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def numero_de_nombre(name: str) -> int | None:
    stem = Path(name).stem
    folded = fold(stem).replace("º", "o").replace("°", "o")
    candidatos: list[int] = []
    for rx in (RE_N, RE_CONFLICTOS_N):
        for m in rx.finditer(folded):
            n = int(m.group(1))
            if 1 <= n <= 320:
                candidatos.append(n)
    if not candidatos:
        # conflictos_sociales42.pdf ya entra en RE_CONFLICTOS_N; respaldo
        m = re.search(r"(\d{1,3})$", folded.replace(" ", "_"))
        if m:
            n = int(m.group(1))
            if 1 <= n <= 320:
                candidatos.append(n)
    # Preferir el que aparece junto a N°; si hay varios, el primero razonable
    # Evitar 12 de "Julio-12" si ya hay un N-101
    if not candidatos:
        return None
    # Si hay un número >= 50 (serie moderna) y otro chico, quedarse con el grande
    grandes = [n for n in candidatos if n >= 50]
    if grandes:
        return grandes[0]
    return candidatos[0]


def clave_nombre(name: str) -> str:
    s = fold(Path(name).stem)
    s = s.replace("pdfs/", "")
    s = re.sub(r"[^a-z0-9]+", "", s)
    s = s.replace("reportemensualde", "").replace("reportede", "")
    return s


def parse_drive(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0]
        size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        md5 = parts[2] if len(parts) > 2 else ""
        fid = parts[3] if len(parts) > 3 else ""
        base = name.split("/")[-1]
        rows.append(
            {
                "origen": "drive",
                "archivo": base,
                "ruta": name,
                "numero": numero_de_nombre(base),
                "size": size,
                "md5": md5,
                "id": fid,
                "clave": clave_nombre(base),
            }
        )
    return rows


def parse_local(carpeta: Path) -> list[dict]:
    manifiesto = {}
    csv_path = carpeta / "manifiesto.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                manifiesto[r["archivo"]] = r
    rows = []
    for pdf in sorted(carpeta.glob("*.pdf")):
        meta = manifiesto.get(pdf.name, {})
        n_meta = meta.get("numero") or ""
        n = int(n_meta) if str(n_meta).isdigit() else numero_de_nombre(pdf.name)
        if n is None:
            n = numero_de_nombre(pdf.name)
        rows.append(
            {
                "origen": "nuevo",
                "archivo": pdf.name,
                "ruta": str(pdf),
                "numero": n,
                "size": pdf.stat().st_size,
                "sha256": meta.get("sha256", ""),
                "clave": clave_nombre(pdf.name),
            }
        )
    return rows


def index_por_numero(rows: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        if r["numero"] is not None:
            out[int(r["numero"])].append(r)
    return out


def main() -> None:
    drive = parse_drive(DRIVE_LIST)
    local = parse_local(LOCAL_DIR)
    d_num = index_por_numero(drive)
    l_num = index_por_numero(local)
    set_d = set(d_num)
    set_l = set(l_num)
    match = sorted(set_d & set_l)
    solo_drive = sorted(set_d - set_l)
    solo_nuevo = sorted(set_l - set_l.intersection(set_d))
    sin_num_d = [r["archivo"] for r in drive if r["numero"] is None]
    sin_num_l = [r["archivo"] for r in local if r["numero"] is None]

    print("=== Inventario ===")
    print(f"Drive (Minería / 01_Datos / crudos / defensoria_pdfs): {len(drive)} archivos, {len(set_d)} con número")
    print(f"Descarga parcial (99_archivo/descarga_web_parcial): {len(local)} archivos, {len(set_l)} con número")
    print()
    print("=== Cruce por número de reporte ===")
    print(f"Coinciden (estaban en Drive y también se bajaron ahora): {len(match)}")
    if match:
        print(f"  rango coincidente: n.{match[0]} – n.{match[-1]}")
    print(f"Solo en Drive (no salieron en la descarga web): {len(solo_drive)}")
    print(f"Solo en la descarga nueva (no estaban en Drive): {len(solo_nuevo)}")
    print()
    if solo_drive:
        print("Solo Drive:", ", ".join(f"n.{n}" for n in solo_drive))
    print()
    if solo_nuevo:
        print("Solo nuevos (los que te faltaban en la carpeta de Minería):")
        # split antiguos vs actuales relative to max drive
        max_drive = max(set_d) if set_d else 0
        actuales = [n for n in solo_nuevo if n > max_drive]
        huecos = [n for n in solo_nuevo if n <= max_drive]
        print(f"  Más actuales que el último de Drive (Drive max n.{max_drive}): {len(actuales)}")
        print("   ", ", ".join(f"n.{n}" for n in actuales))
        print(f"  Huecos / más viejos que también trajo la web y Drive no tenía: {len(huecos)}")
        print("   ", ", ".join(f"n.{n}" for n in huecos))
    print()
    print(f"Sin número parseable — Drive: {len(sin_num_d)}  nuevos: {len(sin_num_l)}")
    for a in sin_num_d:
        print("  D ", a)
    for a in sin_num_l:
        print("  N ", a)

    # CSV
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["numero", "en_drive", "en_nuevo", "estado", "archivo_drive", "archivo_nuevo"])
        todos = sorted(set_d | set_l)
        for n in todos:
            ed = n in set_d
            en = n in set_l
            if ed and en:
                estado = "match"
            elif ed:
                estado = "solo_drive"
            else:
                estado = "solo_nuevo"
            ad = d_num[n][0]["archivo"] if ed else ""
            an = l_num[n][0]["archivo"] if en else ""
            w.writerow([n, ed, en, estado, ad, an])
    print(f"\nTabla: {OUT}")


if __name__ == "__main__":
    main()
