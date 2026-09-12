"""Baja los PDF que el consolidado aún no tenía (Drive saltados + web con nombre raro)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from rutas import INVENTARIO_CSV, PDFS

DEST = PDFS
TOKENS = Path.home() / ".config/google-workspace-mcp/tokens.json"
MCP = Path.home() / ".cursor/mcp.json"
UA = (
    "Mozilla/5.0 (compatible; UP-research/1.0; Universidad del Pacifico; "
    "descarga de reportes publicos de conflictos sociales)"
)


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
        "https://oauth2.googleapis.com/token", data=body, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["access_token"]


def iri_a_uri(url: str) -> str:
    partes = urllib.parse.urlsplit(url)
    ruta = urllib.parse.quote(urllib.parse.unquote(partes.path), safe="/-._~")
    query = urllib.parse.quote(urllib.parse.unquote(partes.query), safe="=&%+-._~")
    return urllib.parse.urlunsplit(
        (partes.scheme, partes.netloc, ruta, query, partes.fragment)
    )


def bajar_http(url: str, dest: Path) -> None:
    req = urllib.request.Request(
        iri_a_uri(url), headers={"User-Agent": UA, "Accept": "*/*"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def bajar_drive(file_id: str, dest: Path, access: str) -> None:
    url = (
        "https://www.googleapis.com/drive/v3/files/"
        + urllib.parse.quote(file_id)
        + "?alt=media&supportsAllDrives=true"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)

    falso_169 = DEST / "Reporte-Mensual-de-Conflictos-Sociales-N_-169---Marzo-2018.pdf"
    if falso_169.exists():
        renamed = DEST / "MALNOMBRADO_es_N156_Febrero2017__N_-169---Marzo-2018.pdf"
        if not renamed.exists():
            falso_169.rename(renamed)
            print(f"Renombrado falso 169 -> {renamed.name}")

    access = token_drive()
    drive = [
        ("1aZc5TOG8ZXy3Yd-rZ6GKKdAsj1LHLbYt", "reporte-69.pdf"),
        (
            "1MTd-Ump8qDoFlLbGI2TbKcPhlc-h8SIG",
            "Reporte-Mensual-de-Conflictos-Sociales-N-169-Marzo-2018.pdf",
        ),
    ]
    for fid, name in drive:
        dest = DEST / name
        if dest.exists() and dest.stat().st_size > 10000:
            print(f"ya estaba {name} ({dest.stat().st_size})")
            continue
        bajar_drive(fid, dest, access)
        print(f"Drive {name} {dest.stat().st_size}")

    web = [
        (
            "https://www.defensoria.gob.pe/wp-content/uploads/2025/03/RCS-N°-252-Feb-2025.pdf",
            "RCS-N-252-Feb-2025.pdf",
        ),
        (
            "https://www.defensoria.gob.pe/wp-content/uploads/2025/12/10.pdf.pdf",
            "Reporte-Conflictos-Sociales-N-261-Noviembre-2025.pdf",
        ),
        (
            "https://www.defensoria.gob.pe/wp-content/uploads/2026/02/10.pdf",
            "Reporte-Conflictos-Sociales-N-263-Enero-2026.pdf",
        ),
    ]
    for url, name in web:
        dest = DEST / name
        if dest.exists() and dest.stat().st_size > 10000:
            print(f"ya estaba {name} ({dest.stat().st_size})")
            continue
        bajar_http(url, dest)
        print(f"Web {name} {dest.stat().st_size}")

    n = len(list(DEST.glob("*.pdf")))
    print(f"Total PDF en carpeta: {n}")

    inv = INVENTARIO_CSV
    if inv.exists():
        existentes = {r.split(",")[0] for r in inv.read_text(encoding="utf-8").splitlines()[1:] if r.strip()}
        extras = []
        mapa = {
            "reporte-69.pdf": ("drive", "1aZc5TOG8ZXy3Yd-rZ6GKKdAsj1LHLbYt"),
            "Reporte-Mensual-de-Conflictos-Sociales-N-169-Marzo-2018.pdf": (
                "drive",
                "1MTd-Ump8qDoFlLbGI2TbKcPhlc-h8SIG",
            ),
            "RCS-N-252-Feb-2025.pdf": ("web", ""),
            "Reporte-Conflictos-Sociales-N-261-Noviembre-2025.pdf": ("web", ""),
            "Reporte-Conflictos-Sociales-N-263-Enero-2026.pdf": ("web", ""),
        }
        for name, (fuente, fid) in mapa.items():
            if name not in existentes and (DEST / name).exists():
                extras.append(f"{name},{fuente},{fid}")
        if extras:
            with inv.open("a", encoding="utf-8", newline="") as fh:
                fh.write("\n".join(extras) + "\n")
            print(f"Inventario +{len(extras)}")


if __name__ == "__main__":
    main()
