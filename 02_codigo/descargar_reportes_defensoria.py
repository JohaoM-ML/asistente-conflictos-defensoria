"""
Descarga los reportes mensuales de conflictos sociales de la Defensoría
del Pueblo, en crudo (el PDF original, sin recortar ni pasar a Excel).

Fuentes oficiales:
  - https://www.defensoria.gob.pe/categorias_de_documentos/reportes/
  - https://www.gob.pe/institucion/defensoria/colecciones/1356-reportes-de-conflictos-sociales

Uso:
  python 02_codigo/descargar_reportes_defensoria.py --solo-listar
  python 02_codigo/descargar_reportes_defensoria.py
  python 02_codigo/descargar_reportes_defensoria.py --max 5
"""

from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path

print = functools.partial(print, flush=True)

USER_AGENT = (
    "Mozilla/5.0 (compatible; UP-research/1.0; Universidad del Pacifico; "
    "descarga de reportes publicos de conflictos sociales)"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}

LISTADO_DEFENSORIA = (
    "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/"
)
BUSQUEDA_GOBPE = "https://www.gob.pe/busquedas.json"

# Títulos que sí son el reporte mensual nacional.
RE_TITULO_OK = re.compile(
    r"reporte\s+(mensual\s+de\s+)?conflictos\s+sociales",
    re.IGNORECASE,
)
RE_TITULO_NO = re.compile(
    r"crisis\s+pol[ií]tica|igualdad\s+y\s+no\s+violencia|"
    r"personas\s+defensoras|mapas?\s+de\s+la\s+corrupci|"
    r"espacios\s+anticorrupci|derecho\s+a\s+la\s+salud",
    re.IGNORECASE,
)
RE_NUMERO = re.compile(
    r"n[°ºo.\s-]*\s*(\d{1,3})\b",
    re.IGNORECASE,
)
RE_PDF = re.compile(
    r"https://www\.defensoria\.gob\.pe/wp-content/uploads/[^\"'\s>]+\.pdf",
    re.IGNORECASE,
)
RE_CARD = re.compile(
    r'<div class="card mb-3 col-12">(?P<body>.*?)</div>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
RE_CARD_TITLE = re.compile(
    r'<a href="(?P<href>[^"]+)"[^>]*>\s*<h4[^>]*>(?P<title>.*?)</h4>',
    re.IGNORECASE | re.DOTALL,
)
RE_CARD_DATE = re.compile(
    r'<h6[^>]*class="card-subtitle[^"]*"[^>]*>\s*<strong>(?P<fecha>.*?)</strong>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class Hallazgo:
    titulo: str
    url: str
    fuente: str
    fecha_publicacion: str = ""
    numero: str = ""
    archivo: str = ""
    bytes: int = 0
    sha256: str = ""
    estado: str = "pendiente"


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def limpiar_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def es_reporte_mensual(titulo: str, url: str) -> bool:
    blob = f"{titulo} {urllib.parse.unquote(url)}"
    if RE_TITULO_NO.search(blob):
        return False
    if RE_TITULO_OK.search(blob):
        return True
    # Nombres viejos de archivo, sin la frase completa en el título.
    nombre = fold(Path(urllib.parse.urlparse(url).path).name)
    return "conflicto" in nombre and "crisis" not in nombre and nombre.endswith(".pdf")


def extraer_numero(titulo: str, url: str) -> str:
    for blob in (titulo, urllib.parse.unquote(url)):
        match = RE_NUMERO.search(blob)
        if match:
            return str(int(match.group(1)))
    return ""


def nombre_archivo(url: str, numero: str) -> str:
    raw = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
    raw = re.sub(r"[^\w.\-]+", "_", raw, flags=re.UNICODE)
    if not raw.lower().endswith(".pdf"):
        raw = (raw or "reporte") + ".pdf"
    if numero and not re.search(rf"(?<!\d){re.escape(numero)}(?!\d)", raw):
        raw = f"n{numero}_{raw}"
    return raw


def iri_a_uri(url: str) -> str:
    """Percent-encode caracteres no ASCII (N°, n.º) para urllib en Windows."""
    partes = urllib.parse.urlsplit(url)
    ruta = urllib.parse.quote(urllib.parse.unquote(partes.path), safe="/-._~")
    query = urllib.parse.quote(urllib.parse.unquote(partes.query), safe="=&%+-._~")
    return urllib.parse.urlunsplit(
        (partes.scheme, partes.netloc, ruta, query, partes.fragment)
    )


def http_get(url: str, timeout: int = 60) -> tuple[bytes, str]:
    req = urllib.request.Request(iri_a_uri(url), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        return resp.read(), ctype


def get_text(url: str) -> str:
    body, _ = http_get(url)
    return body.decode("utf-8", "replace")


def get_json(url: str) -> dict:
    body, _ = http_get(url)
    return json.loads(body.decode("utf-8"))


def paginas_listado(html: str) -> int:
    nums = [int(n) for n in re.findall(r"/reportes/page/(\d+)/", html)]
    return max(nums) if nums else 1


def recolectar_defensoria(pausa: float, max_paginas: int | None) -> list[Hallazgo]:
    hallados: list[Hallazgo] = []
    vistos: set[str] = set()
    html = get_text(LISTADO_DEFENSORIA)
    ultima = paginas_listado(html)
    if max_paginas:
        ultima = min(ultima, max_paginas)
    print(f"[defensoria.gob.pe] páginas de listado: {ultima}")

    for page in range(1, ultima + 1):
        url = LISTADO_DEFENSORIA if page == 1 else f"{LISTADO_DEFENSORIA}page/{page}/"
        try:
            html = get_text(url) if page > 1 else html
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                break
            raise
        nuevos = 0
        for card in RE_CARD.finditer(html):
            body = card.group("body")
            title_m = RE_CARD_TITLE.search(body)
            if not title_m:
                continue
            href = unescape(title_m.group("href")).strip()
            titulo = limpiar_html(title_m.group("title"))
            fecha_m = RE_CARD_DATE.search(body)
            fecha = limpiar_html(fecha_m.group("fecha")) if fecha_m else ""
            if not href.lower().endswith(".pdf"):
                continue
            if not es_reporte_mensual(titulo, href):
                continue
            if href in vistos:
                continue
            vistos.add(href)
            numero = extraer_numero(titulo, href)
            hallados.append(
                Hallazgo(
                    titulo=titulo,
                    url=href,
                    fuente="defensoria.gob.pe",
                    fecha_publicacion=fecha,
                    numero=numero,
                    archivo=nombre_archivo(href, numero),
                )
            )
            nuevos += 1
        # Respaldo: PDFs sueltos que no entraron en el regex de cards.
        for href in RE_PDF.findall(html):
            href = unescape(href)
            if href in vistos:
                continue
            if not es_reporte_mensual("", href):
                continue
            vistos.add(href)
            numero = extraer_numero("", href)
            hallados.append(
                Hallazgo(
                    titulo=Path(urllib.parse.unquote(href)).name,
                    url=href,
                    fuente="defensoria.gob.pe",
                    numero=numero,
                    archivo=nombre_archivo(href, numero),
                )
            )
            nuevos += 1
        print(f"  página {page}/{ultima}: +{nuevos} (acumulado {len(hallados)})")
        time.sleep(pausa)
        html = ""  # forzar descarga en la siguiente
    return hallados


def recolectar_gobpe(pausa: float, max_paginas: int | None) -> list[Hallazgo]:
    hallados: list[Hallazgo] = []
    vistos: set[str] = set()
    sheet = 1
    hojas_vacias = 0
    while True:
        if max_paginas and sheet > max_paginas:
            break
        params = {
            "term": "reporte mensual conflictos sociales",
            "contenido[]": "publicaciones",
            "institucion[]": "defensoria",
            "sheet": str(sheet),
        }
        url = BUSQUEDA_GOBPE + "?" + urllib.parse.urlencode(params)
        data = get_json(url)
        results = data.get("data", {}).get("attributes", {}).get("results") or []
        if not results:
            break
        nuevos = 0
        for item in results:
            titulo = limpiar_html(item.get("name_with_parent") or item.get("content") or "")
            pdf = item.get("action_url") or ""
            fecha = item.get("publication") or ""
            colecciones = item.get("collections") or []
            en_coleccion = any(int(c.get("id") or 0) == 1356 for c in colecciones)
            if not pdf.lower().endswith(".pdf"):
                continue
            if not (en_coleccion or es_reporte_mensual(titulo, pdf)):
                continue
            if not es_reporte_mensual(titulo, pdf) and not en_coleccion:
                continue
            if RE_TITULO_NO.search(titulo):
                continue
            if not es_reporte_mensual(titulo, pdf):
                # Colección 1356 a veces mezcla otros reportes; nos quedamos
                # solo con los de conflictos sociales.
                continue
            if pdf in vistos:
                continue
            vistos.add(pdf)
            numero = extraer_numero(titulo, pdf)
            hallados.append(
                Hallazgo(
                    titulo=titulo,
                    url=pdf,
                    fuente="gob.pe",
                    fecha_publicacion=fecha,
                    numero=numero,
                    archivo=nombre_archivo(pdf, numero),
                )
            )
            nuevos += 1
        total = data.get("data", {}).get("attributes", {}).get("total_count")
        print(f"[gob.pe] hoja {sheet}: +{nuevos} (acumulado {len(hallados)}; total búsqueda {total})")
        if nuevos == 0:
            hojas_vacias += 1
        else:
            hojas_vacias = 0
        if len(results) < 25 or hojas_vacias >= 8:
            break
        sheet += 1
        time.sleep(pausa)
    return hallados


def clave(item: Hallazgo) -> str:
    if item.numero:
        return f"n{item.numero}"
    return fold(item.archivo)


def fusionar(bloques: list[list[Hallazgo]]) -> list[Hallazgo]:
    por_clave: dict[str, Hallazgo] = {}
    sin_numero: list[Hallazgo] = []
    for bloque in bloques:
        for item in bloque:
            if not item.numero:
                sin_numero.append(item)
                continue
            actual = por_clave.get(clave(item))
            if actual is None:
                por_clave[clave(item)] = item
                continue
            # Preferir defensoria.gob.pe (sitio de la institución) si hay dos URLs.
            if actual.fuente == "gob.pe" and item.fuente == "defensoria.gob.pe":
                por_clave[clave(item)] = item
    vistos_url = {i.url for i in por_clave.values()}
    extra = []
    for item in sin_numero:
        if item.url in vistos_url:
            continue
        vistos_url.add(item.url)
        extra.append(item)
    ordenados = sorted(
        list(por_clave.values()) + extra,
        key=lambda x: (int(x.numero) if x.numero.isdigit() else -1, x.titulo),
    )
    return ordenados


def descargar(item: Hallazgo, carpeta: Path, pausa: float) -> Hallazgo:
    destino = carpeta / item.archivo
    if destino.exists() and destino.stat().st_size > 1000:
        item.bytes = destino.stat().st_size
        item.sha256 = hashlib.sha256(destino.read_bytes()).hexdigest()
        item.estado = "ya_estaba"
        return item
    try:
        body, ctype = http_get(item.url, timeout=120)
    except Exception as exc:
        item.estado = f"error: {exc}"
        return item
    if "pdf" not in ctype.lower() and not body.startswith(b"%PDF"):
        item.estado = f"no_es_pdf ({ctype})"
        return item
    destino.write_bytes(body)
    item.bytes = len(body)
    item.sha256 = hashlib.sha256(body).hexdigest()
    item.estado = "descargado"
    time.sleep(pausa)
    return item


def guardar_manifiesto(items: list[Hallazgo], carpeta: Path) -> None:
    campos = [
        "numero",
        "titulo",
        "fuente",
        "fecha_publicacion",
        "url",
        "archivo",
        "bytes",
        "sha256",
        "estado",
    ]
    csv_path = carpeta / "manifiesto.csv"
    jsonl_path = carpeta / "manifiesto.jsonl"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        for item in items:
            writer.writerow({k: getattr(item, k) for k in campos})
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    raiz = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Descarga PDF crudos de reportes mensuales de conflictos sociales."
    )
    parser.add_argument(
        "--salida",
        default=str(raiz / "01_datos" / "crudos" / "pdfs"),
        help="Carpeta donde guardar los PDF y el manifiesto.",
    )
    parser.add_argument("--solo-listar", action="store_true")
    parser.add_argument("--max", type=int, default=0, help="Tope de archivos a descargar (0 = todos).")
    parser.add_argument("--pausa", type=float, default=1.2, help="Segundos entre pedidos HTTP.")
    parser.add_argument(
        "--fuente",
        choices=("ambas", "defensoria", "gobpe"),
        default="ambas",
    )
    parser.add_argument(
        "--max-paginas",
        type=int,
        default=0,
        help="Tope de páginas/hojas por fuente (0 = todas). Útil para pruebas.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    max_paginas = args.max_paginas or None

    bloques: list[list[Hallazgo]] = []
    if args.fuente in ("ambas", "defensoria"):
        bloques.append(recolectar_defensoria(args.pausa, max_paginas))
    if args.fuente in ("ambas", "gobpe"):
        bloques.append(recolectar_gobpe(args.pausa, max_paginas))

    items = fusionar(bloques)
    print(f"\nÚnicos (reporte mensual de conflictos): {len(items)}")
    if args.max:
        items = items[: args.max]
        print(f"Recorte --max {args.max}: {len(items)}")

    if args.solo_listar:
        for item in items:
            print(f"  n{item.numero or '?'}\t{item.fuente}\t{item.titulo[:80]}\t{item.url}")
        guardar_manifiesto(items, carpeta)
        print(f"\nManifiesto (sin descargar): {carpeta / 'manifiesto.csv'}")
        return 0

    ok = 0
    for i, item in enumerate(items, 1):
        item = descargar(item, carpeta, args.pausa)
        items[i - 1] = item
        marca = "OK" if item.estado in {"descargado", "ya_estaba"} else "FAIL"
        if item.estado in {"descargado", "ya_estaba"}:
            ok += 1
        print(f"[{i}/{len(items)}] {marca} n{item.numero or '?'} {item.archivo} ({item.estado})")
        if i % 10 == 0:
            guardar_manifiesto(items, carpeta)

    guardar_manifiesto(items, carpeta)
    print(f"\nListos: {ok}/{len(items)}")
    print(f"Carpeta: {carpeta}")
    print("Estos PDF son el reporte mensual nacional, no un archivo por mina.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
