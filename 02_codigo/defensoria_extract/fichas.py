from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .layout import Bloque, es_departamento, fold, norm_ws
from .secciones import estado_de_bloque

CAMPOS = [
    "codigo",
    "tipo",
    "ingreso_como",
    "caso",
    "ubicacion",
    "actores_primarios",
    "actores_secundarios",
    "actores_terciarios",
    "actores",
    "hechos_del_mes",
]

# Etiquetas ancladas al inicio de línea (evita "como caso nuevo").
_NEXT = (
    r"tipo|caso|ubicaci[oó]n|ingres[oó]|c[oó]digo|"
    r"actores?\s+primarios?|actores?\s+secundarios?|actores?\s+terciarios?|"
    r"actores\b|hechos|antecedentes|autoridad|poblaci[oó]n|motivo|fecha|"
    r"cuestionamiento"
)


def _campo(label: str) -> re.Pattern:
    return re.compile(
        rf"(?ims)^(?:{label})\s*[:.]?\s*(.*?)(?=^(?:{_NEXT})\b|\Z)"
    )


# Límites de recorte. El texto íntegro de la ficha vive en texto_crudo, que es
# además el insumo de la capa LLM, así que conviene que sea generoso.
MAX_CASO_FALLBACK = 2500
MAX_TEXTO_CRUDO = 12000

RE_TIPO = _campo(r"tipo")
RE_CODIGO = _campo(r"c[oó]digo")
# El separador es obligatorio y se excluyen los badges "CASO NUEVO"/"CASO
# REACTIVADO" que los PDF imprimen como etiqueta visual sobre la ficha. Con el
# separador opcional esos badges ganaban sobre el "Caso:" real de más abajo y
# dejaban "NUEVO" como descripción del conflicto en 1330 filas.
RE_CASO = re.compile(
    rf"(?ims)^caso\s*(?!nuevo\b|reactivado\b)[:.]\s*(.*?)(?=^(?:{_NEXT})\b|\Z)"
)
RE_UBI = _campo(r"ubicaci[oó]n")
RE_AP = _campo(r"actores?\s+primarios?")
RE_AS = _campo(r"actores?\s+secundarios?")
RE_AT = _campo(r"actores?\s+terciarios?")
RE_ACT = _campo(r"actores")
RE_INGRESO = re.compile(
    r"(?ims)^ingres[oó]\s+como(?:\s+caso)?(?:\s+(nuevo|reactivado))?\s*[:.]?\s*(.*?)(?=^"
    + _NEXT
    + r"\b|\Z)"
)
RE_MOTIVO = _campo(r"motivo|cuestionamientos?")
RE_AUTORIDAD = _campo(r"autoridad")
RE_POB = _campo(r"poblaci[oó]n")
RE_HECHOS = _campo(r"hechos|antecedentes")


def _limpio(s: str) -> str:
    s = html.unescape(s or "")
    s = norm_ws(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .;\u00a0")


RE_BADGE_INGRESO = re.compile(r"(?im)^caso\s+(nuevo|reactivado)\b")


def _recortar(texto: str, limite: int) -> str:
    """Recorta en frontera de oración para no cortar a mitad de palabra."""
    t = texto or ""
    if len(t) <= limite:
        return t
    corte = t[:limite]
    for sep in (". ", "; ", ", "):
        pos = corte.rfind(sep)
        if pos >= limite * 0.6:
            return corte[: pos + 1].strip()
    pos = corte.rfind(" ")
    return (corte[:pos] if pos > 0 else corte).strip()


def _pre(texto: str) -> str:
    t = texto or ""
    t = t.replace("\u00ad", "")
    t = re.sub(r"(?i)actores\s+primarios", "Actores primarios", t)
    t = re.sub(r"(?i)actores\s+secundarios", "Actores secundarios", t)
    t = re.sub(r"(?i)actores\s+terciarios", "Actores terciarios", t)
    t = re.sub(
        r"(?i)\s+(?=(tipo|ubicaci[oó]n|actores?\s+primarios?|actores?\s+secundarios?|actores?\s+terciarios?|ingres[oó]\s+como|c[oó]digo)\s*[:.])",
        "\n",
        t,
    )
    t = re.sub(r"(?i)(?<!como )\s+(?=caso\s*[:.])", "\n", t)
    return t


def parsear_ficha(texto: str, hechos: str = "") -> dict:
    t = _pre(texto)
    out = {k: "" for k in CAMPOS}
    m = RE_TIPO.search(t)
    if m:
        out["tipo"] = _limpio(m.group(1))
        out["tipo"] = re.split(r"(?i)\s+ingres", out["tipo"])[0].strip(" .;")
        out["tipo"] = out["tipo"][:160]
    m = RE_CODIGO.search(t)
    if m:
        out["codigo"] = _limpio(m.group(1))
    m = RE_INGRESO.search(t)
    if m:
        etiqueta = (m.group(1) or "").lower()
        extra = _limpio(m.group(2) or "")
        out["ingreso_como"] = (etiqueta + (" " + extra if extra else "")).strip()
    if not out["ingreso_como"]:
        m = RE_BADGE_INGRESO.search(t)
        if m:
            out["ingreso_como"] = m.group(1).lower()
    m = RE_CASO.search(t)
    if m:
        out["caso"] = _limpio(m.group(1))
    m = RE_UBI.search(t)
    if m:
        out["ubicacion"] = _limpio(m.group(1))
    m = RE_AP.search(t)
    if m:
        out["actores_primarios"] = _limpio(m.group(1))
    m = RE_AS.search(t)
    if m:
        out["actores_secundarios"] = _limpio(m.group(1))
    m = RE_AT.search(t)
    if m:
        out["actores_terciarios"] = _limpio(m.group(1))
    if not out["actores_primarios"]:
        m = RE_ACT.search(t)
        if m:
            out["actores"] = _limpio(m.group(1))
    if not out["actores"]:
        m = RE_AUTORIDAD.search(t)
        if m:
            out["actores"] = _limpio(m.group(1))
    if not out["ubicacion"]:
        m = RE_POB.search(t)
        if m:
            out["ubicacion"] = _limpio(m.group(1))
    if not out["caso"]:
        m = RE_MOTIVO.search(t)
        if m:
            out["caso"] = _limpio(m.group(1))
    m = RE_HECHOS.search(t)
    hechos_campo = _limpio(m.group(1)) if m else ""
    out["hechos_del_mes"] = _limpio(hechos) or hechos_campo
    if not out["caso"] and hechos_campo:
        out["caso"] = _recortar(hechos_campo, MAX_CASO_FALLBACK)
    if not out["caso"]:
        for p in re.split(r"\n\s*\n", t):
            p = _limpio(p)
            if len(p) > 40 and not fold(p).startswith(("tipo", "codigo", "caso n")):
                out["caso"] = _recortar(p, MAX_CASO_FALLBACK)
                break
    return out


def es_inicio_ficha(txt: str, numerados: bool = False) -> bool:
    s = txt.strip()
    t = re.sub(r"\s+", " ", fold(s))
    if t in {"caso nuevo", "caso reactivado"}:
        return True
    if re.match(r"^tipo\s*[:.]", s, re.I):
        return True
    if re.match(r"^c[oó]digo\s*[:.]", s, re.I):
        return True
    if re.match(r"^casos?\s+n[°ºo.\s]*\d+", s, re.I):
        return True
    if numerados and re.match(r"^\d{1,3}\.\s+\S", s) and not re.match(r"^\d+\.\d+", s):
        return True
    return False


def _es_inicio_ficha_suave(txt: str) -> bool:
    """Anclas de apertura cuando Tipo:/Código: quedaron en la página anterior (2024+)."""
    s = txt.strip()
    if re.match(r"^ingres[oó]\s+como\b", s, re.I):
        return True
    if re.match(r"^caso\s*(?!nuevo\b|reactivado\b)[:.]", s, re.I):
        return True
    return False


def _es_badge(txt: str) -> bool:
    t = re.sub(r"\s+", " ", fold(txt)).strip()
    return t in {
        "caso nuevo",
        "caso reactivado",
        "hay dialogo",
        "no hay dialogo",
        "hay diálogo",
        "no hay diálogo",
    }


def _trozos_izquierda(texto: str) -> list[str]:
    partes = re.split(r"(?i)(?=\btipo\s*[:.])", texto)
    return [p.strip() for p in partes if p.strip()]


def _espera_tipo(curr: "_Abierta") -> bool:
    joined = "\n".join(curr.left)
    return not re.search(r"(?im)^tipo\s*[:.]", joined)


def _curr_tiene_caso(curr: "_Abierta") -> bool:
    joined = "\n".join(curr.left)
    return bool(re.search(r"(?im)^caso\s*(?!nuevo\b|reactivado\b)[:.]", joined))


@dataclass
class _Abierta:
    estado: str
    departamento: str
    pagina: int
    y: float
    left: list[str] = field(default_factory=list)
    right: list[str] = field(default_factory=list)


class ExtractorPaginas:
    """Recorre bloques L/R intercalados y arma fichas que cruzan páginas."""

    def __init__(self) -> None:
        self.dept = ""
        self.estado = "Activo"
        self.curr: _Abierta | None = None
        self.filas: list[dict] = []

    def _flush(self) -> None:
        if not self.curr:
            return
        cuerpo = "\n".join(self.curr.left)
        hechos = " ".join(self.curr.right)
        if _es_badge(cuerpo) or len(cuerpo) < 12:
            self.curr = None
            return
        ficha = parsear_ficha(cuerpo, hechos)
        ficha["departamento"] = self.curr.departamento
        ficha["estado"] = self.curr.estado
        ficha["texto_crudo"] = norm_ws(cuerpo)[:MAX_TEXTO_CRUDO]
        ficha["pagina"] = self.curr.pagina
        if ficha["caso"] or ficha["tipo"] or ficha["codigo"] or len(cuerpo) > 80:
            if fold(ficha.get("caso") or "").startswith("defensoria del pueblo"):
                self.curr = None
                return
            if ficha["caso"] and re.match(r"^\d+\.", ficha["caso"]):
                ficha["caso"] = re.sub(r"^\d+\.\s*", "", ficha["caso"])
            self.filas.append(ficha)
        self.curr = None

    def _abrir(self, bloque: Bloque, texto: str) -> None:
        self._flush()
        self.curr = _Abierta(
            estado=self.estado,
            departamento=self.dept,
            pagina=bloque.pagina,
            y=bloque.y,
            left=[texto],
        )

    def feed(self, bloques: list[Bloque]) -> None:
        for b in bloques:
            est = estado_de_bloque(b.texto)
            if est and len(b.texto) < 220:
                self.estado = est
                if "mas de un departamento" in fold(b.texto):
                    self.dept = "Multidepartamental"
                continue
            tf = fold(b.texto)
            if tf.startswith("observacion") or tf.startswith("cuadro n"):
                continue
            maybe = es_departamento(b.texto)
            if maybe and len(b.texto) < 48:
                self.dept = maybe
                continue
            if _es_badge(b.texto) and b.col == "R":
                if self.curr:
                    self.curr.right.append(b.texto)
                continue
            if b.col == "R":
                if self.curr:
                    self.curr.right.append(b.texto)
                continue
            for trozo in _trozos_izquierda(b.texto):
                if not trozo.strip():
                    continue
                if es_inicio_ficha(trozo):
                    if self.curr and _espera_tipo(self.curr) and re.match(
                        r"^tipo\s*[:.]", trozo.strip(), re.I
                    ):
                        self.curr.left.append(trozo)
                        continue
                    self._abrir(b, trozo)
                elif self.curr:
                    self.curr.left.append(trozo)
                elif _es_inicio_ficha_suave(trozo) or es_inicio_ficha(
                    trozo.split("\n", 1)[0]
                ):
                    # Sin ficha abierta: Ingreso/Caso pueden abrir si Tipo quedó atrás.
                    self._abrir(b, trozo)

    def finish(self) -> list[dict]:
        self._flush()
        return self.filas


def fichas_desde_columnas(
    left: list[tuple[float, str]],
    right: list[tuple[float, str]],
    departamento: str,
    estado: str,
) -> tuple[list[dict], str]:
    """Compat: una página. Preferir ExtractorPaginas en el CLI."""
    ext = ExtractorPaginas()
    ext.dept = departamento
    ext.estado = estado
    bloques = [Bloque(1, y, 0, 100, "L", t) for y, t in left]
    bloques += [Bloque(1, y, 400, 500, "R", t) for y, t in right]
    bloques.sort(key=lambda b: (b.y, 0 if b.col == "L" else 1))
    ext.feed(bloques)
    filas = ext.finish()
    return filas, ext.dept


def _es_titulo_corrido(ln: str) -> bool:
    t = re.sub(r"\s+", " ", fold(ln)).strip(" :.")
    if t in {
        "anexo",
        "descripcion de los conflictos",
        "conflictos activos",
        "conflictos latentes",
        "conflictos resueltos",
        "conflictos concluidos",
        "conflictos vigentes",
        "nuevos casos",
        "1. nuevos casos",
        "2. conflictos vigentes",
        "3. conflictos concluidos",
    }:
        return True
    if re.match(r"^\d+\s+anexo", t):
        return True
    return False


def fichas_texto_corrido(texto: str, estado: str, departamento: str) -> tuple[list[dict], str]:
    dept = departamento
    est = estado
    lineas = [ln.strip() for ln in (texto or "").splitlines()]
    bloques: list[tuple[str, str, list[str]]] = []
    actual: list[str] = []
    for ln in lineas:
        if not ln:
            continue
        if re.fullmatch(r"\d{1,3}", ln):
            continue
        est_b = estado_de_bloque(ln)
        if est_b and len(ln) < 80:
            if actual:
                bloques.append((dept, est, actual))
                actual = []
            est = est_b
            continue
        if _es_titulo_corrido(ln):
            continue
        maybe = es_departamento(ln)
        if maybe and len(ln) < 48:
            if actual:
                bloques.append((dept, est, actual))
                actual = []
            dept = maybe
            continue
        if re.match(r"^\d{1,3}\.$", ln) and actual:
            bloques.append((dept, est, actual))
            actual = [ln]
            continue
        if re.match(r"^\d{1,3}\.\s+\S", ln) and actual:
            bloques.append((dept, est, actual))
            actual = [ln]
            continue
        if es_inicio_ficha(ln, numerados=True) and actual:
            bloques.append((dept, est, actual))
            actual = [ln]
            continue
        actual.append(ln)
    if actual:
        bloques.append((dept, est, actual))

    out = []
    for d, e, lns in bloques:
        cuerpo = "\n".join(lns)
        if len(cuerpo) < 40:
            continue
        if _es_titulo_corrido(cuerpo) or fold(cuerpo).startswith("anexo"):
            continue
        ficha = parsear_ficha(cuerpo, "")
        ficha["departamento"] = d
        ficha["estado"] = e
        ficha["texto_crudo"] = norm_ws(cuerpo)[:MAX_TEXTO_CRUDO]
        if ficha["caso"] and re.match(r"^\d+\.", ficha["caso"]):
            ficha["caso"] = re.sub(r"^\d+\.\s*", "", ficha["caso"])
        if fold(ficha.get("caso") or "").startswith("defensoria del pueblo"):
            continue
        if ficha["caso"] or ficha["tipo"]:
            out.append(ficha)
        elif len(cuerpo) > 120:
            ficha["caso"] = _recortar(_limpio(cuerpo), MAX_CASO_FALLBACK)
            out.append(ficha)
    return out, dept


# Tipos frecuentes en tablas compactas de latentes (sin "Tipo:" como etiqueta de línea).
_TIPOS_LATENTE = (
    "socioambiental",
    "sociambiental",
    "asuntos de gobierno local",
    "asuntos de gobierno nacional",
    "asuntos de gobierno regional",
    "asunto de gobierno local",
    "asunto de gobierno nacional",
    "demarcacion territorial",
    "demarcación territorial",
    "comunal",
    "laboral",
    "por asuntos de gobierno local",
    "por asuntos de gobierno nacional",
    "por asuntos de gobierno regional",
    "de asuntos de gobierno nacional",
    "de asuntos de gobierno local",
    "otros",
)

_RE_FILA_NUM = re.compile(r"(?:(?<=\n)|^)\s*(\d{1,3})\.\s+")
_RE_FECHA_COMPACTA = re.compile(
    r"^(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*[-\s/]*\d{2,4}\b",
    re.I,
)


def _partir_tipo_final(texto: str) -> tuple[str, str]:
    """Separa descripción y tipo. El tipo es un valor conocido; el resto es caso."""
    t = (texto or "").strip()
    if not t:
        return "", ""
    # "… Tipo socioambiental Descripción larga…"
    m = re.search(r"(?i)\btipo\s+(.+)$", t)
    if m:
        cola = m.group(1).strip()
        caso_pref = _limpio(t[: m.start()])
        low = fold(cola)
        for tip in sorted(_TIPOS_LATENTE, key=len, reverse=True):
            tip_f = fold(tip)
            if low == tip_f or low.startswith(tip_f + " "):
                resto = cola[len(tip) :].lstrip(" .-–—")
                # Si no matcheó por longitud exacta del original, recortar por regex
                mtip = re.match(re.escape(tip) + r"\b[\s.:–—-]*(.*)$", cola, re.I)
                if mtip:
                    resto = mtip.group(1).strip()
                partes = [p for p in (caso_pref, _limpio(resto)) if p]
                return _limpio(" ".join(partes)), tip[:160]
        # Tipo desconocido: primera frase corta como tipo
        primera = re.split(r"(?<=\w)(?=[A-ZÁÉÍÓÚ])|\.\s+", cola, maxsplit=1)
        if len(primera) == 2 and len(primera[0]) < 60:
            return _limpio(caso_pref + " " + primera[1]), _limpio(primera[0])[:160]
        return caso_pref, _limpio(cola)[:160]
    # Tabla 2024+ sin la palabra "Tipo": denominación + tipo al final
    low = fold(t)
    for tip in sorted(_TIPOS_LATENTE, key=len, reverse=True):
        tip_f = fold(tip)
        if low.endswith(tip_f):
            m2 = re.search(re.escape(tip) + r"\s*$", t, re.I)
            if m2:
                return _limpio(t[: m2.start()]), _limpio(m2.group(0))[:160]
    return _limpio(t), ""


def _dept_al_inicio(texto: str) -> tuple[str, str]:
    """Si el texto empieza con un departamento canónico, lo separa."""
    s = (texto or "").strip()
    # Probar nombres largos primero
    from .layout import DEPT_CANON

    candidatos = sorted(DEPT_CANON.keys(), key=len, reverse=True)
    up = s.upper()
    for raw in candidatos:
        if up.startswith(raw) and (len(s) == len(raw) or not s[len(raw)].isalpha()):
            resto = s[len(raw) :].lstrip(" .-–—")
            return DEPT_CANON[raw], resto
    maybe = es_departamento(s.split(",")[0].split(".")[0].strip())
    if maybe and len(s.split()[0]) <= 20:
        # "AMAZONAS Distrito…" ya cubierto arriba; fallback mínimo
        pass
    return "", s


def fichas_tabla_latentes(texto: str, pagina: int = 0) -> list[dict]:
    """Parsea el detalle tabular de latentes (Adjuntía 2009+ e infografía 2024+).

    Formatos observados:
    - 2009–2023: `1. AMAZONAS Distrito … Tipo socioambiental Descripción…`
    - 2024+: `1. Oct-22 Amazonas Kuélap Asuntos de gobierno nacional`
    """
    t = texto or ""
    # Quedarse desde el encabezado de latentes si aparece.
    mhead = re.search(r"(?i)detalle de los conflictos latentes", t)
    if mhead:
        t = t[mhead.start() :]
    # Cortar si empieza otra sección posterior.
    mstop = re.search(
        r"(?i)(?:casos en observaci[oó]n|acciones colectivas de protesta|"
        r"hechos de violencia|actuaciones defensoriales|"
        r"forma de resoluci[oó]n|conflictos que han pasado|"
        r"conflictos(?:\s+\w+){0,4}\s+resueltos|"
        r"viii\.|ix\.|x\.)",
        t[80:] if len(t) > 80 else "",
    )
    if mstop:
        t = t[: 80 + mstop.start()]

    filas_txt = []
    indices = [m.start() for m in _RE_FILA_NUM.finditer(t)]
    if not indices:
        return []
    indices.append(len(t))
    for a, b in zip(indices, indices[1:]):
        trozo = t[a:b].strip()
        trozo = re.sub(r"^\d{1,3}\.\s*", "", trozo)
        trozo = re.sub(r"\s+", " ", trozo).strip()
        if len(trozo) < 8:
            continue
        # Filas vacías del cuadro de reactivados: "1. - -"
        if re.fullmatch(r"[-–—.\s]+", trozo):
            continue
        filas_txt.append(trozo)

    out: list[dict] = []
    for cuerpo in filas_txt:
        resto = cuerpo
        # Fechas: Oct-22 | Ene-12 | 05/2011 | mayo 2021
        mfecha = _RE_FECHA_COMPACTA.match(resto)
        if not mfecha:
            mfecha = re.match(r"^\d{1,2}[/-]\d{2,4}\b", resto)
        if not mfecha:
            mfecha = re.match(
                r"^(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
                r"septiembre|setiembre|octubre|noviembre|diciembre)\s+\d{4}\b",
                resto,
                re.I,
            )
        if mfecha:
            resto = resto[mfecha.end() :].lstrip(" -–—")
        dept, resto = _dept_al_inicio(resto)
        caso, tipo = _partir_tipo_final(resto)
        if not caso and not tipo:
            continue
        fc = fold(caso)
        # Filas basura de cabecera / otras secciones
        if fc.startswith(
            (
                "n ubicacion",
                "n fecha",
                "denominacion del caso",
                "la defensoria del pueblo",
                "lugar caso",
                "forma de resolucion",
            )
        ):
            continue
        if len(caso) < 3 and not tipo:
            continue
        ficha = {k: "" for k in CAMPOS}
        ficha["caso"] = caso[:MAX_CASO_FALLBACK]
        ficha["tipo"] = tipo
        ficha["departamento"] = dept
        ficha["estado"] = "Latente"
        ficha["texto_crudo"] = norm_ws(cuerpo)[:MAX_TEXTO_CRUDO]
        ficha["pagina"] = pagina
        out.append(ficha)
    return out