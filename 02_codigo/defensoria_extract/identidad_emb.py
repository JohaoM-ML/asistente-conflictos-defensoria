"""Identidad de casos por similitud semántica.

Alternativa a `identidad.agrupar`, que compara strings con rapidfuzz. El fuzzy
sobre texto exige que la redacción se parezca, y la Defensoría reescribe la
descripción del mismo conflicto a lo largo de los años, así que fragmenta un
conflicto largo en varios casos distintos. Los embeddings comparan significado
y toleran esa reescritura.

El clustering principal se bloquea por departamento (evita n² nacional y mezcla
de homónimos). Luego dos post-pasos corrigen la inflación artificial:

1. Unir `caso_id` con el mismo `caso_estandarizado` idéntico entre departamentos
   (el campo departamento a menudo viene ruidoso o mal asignado).
2. Puente global a la misma distancia coseno del umbral, sobre representantes
   de cada cluster, para unir reescrituras del mismo conflicto cross-depto.

Si el paso 2 fusiona Afrodita y Dorato (Cenepa), se revierte y solo queda el 1.
"""
from __future__ import annotations

from collections import defaultdict

from .identidad import estandarizar
from .layout import fold

MODELO_DEFECTO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Calibrado con el conflicto de Cenepa (Amazonas), donde la Defensoría describe
# oposición minera de las mismas comunidades frente a dos empresas distintas,
# Afrodita y Dorato Perú. Por debajo de 0.90 el modelo las fusiona en un solo
# caso, lo que borra una distinción que importa para el análisis de minería.
UMBRAL_DEFECTO = 0.90

_modelo_cache: dict[str, object] = {}


def cargar_modelo(nombre: str = MODELO_DEFECTO):
    """Carga perezosa: el modelo pesa ~120 MB y solo hace falta al agrupar."""
    if nombre not in _modelo_cache:
        from sentence_transformers import SentenceTransformer

        _modelo_cache[nombre] = SentenceTransformer(nombre)
    return _modelo_cache[nombre]


def _clusters(vectores, umbral: float) -> list[int]:
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    if len(vectores) == 1:
        return [0]
    modelo = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1.0 - umbral,
    )
    return list(modelo.fit_predict(np.asarray(vectores)))


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, x: int) -> None:
        if x not in self.parent:
            self.parent[x] = x

    def find(self, x: int) -> int:
        self.add(x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _cenepa_ok(filas: list[dict]) -> bool:
    """True si Afrodita y Dorato (Cenepa) quedan en caso_id distintos."""
    afro: set[int] = set()
    dora: set[int] = set()
    for f in filas:
        blob = fold((f.get("caso") or "") + " " + (f.get("texto_crudo") or ""))
        if "cenepa" not in blob:
            continue
        cid = f.get("caso_id")
        if cid is None:
            continue
        if "afrodita" in blob:
            afro.add(int(cid))
        if "dorato" in blob:
            dora.add(int(cid))
    if not afro or not dora:
        return True  # no hay señal; no bloquear
    return afro.isdisjoint(dora)


def _remap_ids(filas: list[dict], uf: _UnionFind) -> None:
    """Reescribe caso_id con representantes densos 1..N."""
    roots = sorted({uf.find(int(f["caso_id"])) for f in filas if f.get("caso_id") is not None})
    nuevo = {r: i + 1 for i, r in enumerate(roots)}
    for f in filas:
        if f.get("caso_id") is not None:
            f["caso_id"] = nuevo[uf.find(int(f["caso_id"]))]


def _merge_claves_identicas(filas: list[dict]) -> _UnionFind:
    """Une caso_id que comparten el mismo caso_estandarizado (texto idéntico)."""
    uf = _UnionFind()
    por_clave: dict[str, list[int]] = defaultdict(list)
    for f in filas:
        cid = f.get("caso_id")
        clave = f.get("caso_estandarizado") or ""
        if cid is None:
            continue
        uf.add(int(cid))
        if clave:
            por_clave[clave].append(int(cid))
    for ids in por_clave.values():
        if len(ids) < 2:
            continue
        base = ids[0]
        for other in ids[1:]:
            uf.union(base, other)
    return uf


def _puente_global(
    filas: list[dict],
    uf: _UnionFind,
    vecs_por_clave: dict[tuple[str, str], object],
    claves_orden: list[tuple[str, str]],
    umbral: float,
) -> _UnionFind:
    """Clustering global sobre un representante por caso_id actual."""
    import numpy as np

    # Representante: clave (dept, texto) del caso_id con el vector ya calculado;
    # elegimos el texto más largo entre las claves del cluster.
    mejor: dict[int, tuple[str, tuple[str, str]]] = {}
    for f in filas:
        cid = uf.find(int(f["caso_id"]))
        dept = (f.get("departamento") or "").upper() or "_"
        clave = f.get("caso_estandarizado") or ""
        if not clave:
            continue
        k = (dept, clave)
        if k not in vecs_por_clave:
            continue
        texto = (f.get("caso") or "").strip()
        prev = mejor.get(cid)
        if prev is None or len(texto) > len(prev[0]):
            mejor[cid] = (texto, k)

    if len(mejor) < 2:
        return uf

    ids = list(mejor.keys())
    mat = np.asarray([vecs_por_clave[mejor[i][1]] for i in ids])
    etiquetas = _clusters(mat, umbral)
    por_et: dict[int, list[int]] = defaultdict(list)
    for cid, et in zip(ids, etiquetas):
        por_et[int(et)].append(cid)
    for grupo in por_et.values():
        if len(grupo) < 2:
            continue
        base = grupo[0]
        for other in grupo[1:]:
            uf.union(base, other)
    return uf


def agrupar(
    filas: list[dict],
    umbral: float = UMBRAL_DEFECTO,
    modelo: str = MODELO_DEFECTO,
    verbose: bool = True,
    puente_global: bool = True,
) -> list[dict]:
    """Asigna `caso_id` y `caso_estandarizado` por similitud semántica."""
    # Una misma descripción se repite muchos meses: se codifica una sola vez.
    repr_de_clave: dict[tuple[str, str], str] = {}
    for f in filas:
        dept = (f.get("departamento") or "").upper() or "_"
        texto = (f.get("caso") or "").strip()
        clave = estandarizar(texto)
        f["caso_estandarizado"] = clave
        f["_dept"] = dept
        f["_clave"] = clave
        if not clave:
            continue
        k = (dept, clave)
        # El texto más largo del grupo es el que más contexto le da al modelo.
        if len(texto) > len(repr_de_clave.get(k, "")):
            repr_de_clave[k] = texto

    if not repr_de_clave:
        for i, f in enumerate(filas):
            f["caso_id"] = i + 1
            f.pop("_clave", None)
            f.pop("_dept", None)
        return filas

    claves = list(repr_de_clave)
    textos = [repr_de_clave[k] for k in claves]
    if verbose:
        print(f"Codificando {len(textos)} descripciones únicas con {modelo}...", flush=True)
    st = cargar_modelo(modelo)
    vecs = st.encode(
        textos,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=verbose,
        convert_to_numpy=True,
    )
    vecs_por_clave = {k: vecs[i] for i, k in enumerate(claves)}

    por_dept: dict[str, list[int]] = defaultdict(list)
    for i, (dept, _) in enumerate(claves):
        por_dept[dept].append(i)

    next_id = 1
    id_de_clave: dict[tuple[str, str], int] = {}
    for dept, idxs in sorted(por_dept.items()):
        etiquetas = _clusters(vecs[idxs], umbral)
        locales: dict[int, int] = {}
        for pos, et in zip(idxs, etiquetas):
            if et not in locales:
                locales[et] = next_id
                next_id += 1
            id_de_clave[claves[pos]] = locales[et]

    for f in filas:
        clave = f.get("_clave", "")
        dept = f.get("_dept", "_")
        if clave:
            f["caso_id"] = id_de_clave[(dept, clave)]
        else:
            f["caso_id"] = next_id
            next_id += 1

    # Post-paso 1: claves estandarizadas idénticas cross-departamento.
    uf = _merge_claves_identicas(filas)
    _remap_ids(filas, uf)
    if verbose:
        n1 = len({f["caso_id"] for f in filas})
        print(f"Tras merge de claves idénticas: {n1} caso_id", flush=True)

    # Snapshot para poder revertir el puente global si rompe Cenepa.
    ids_antes_puente = [f["caso_id"] for f in filas]

    if puente_global:
        uf2 = _UnionFind()
        for f in filas:
            uf2.add(int(f["caso_id"]))
        # Reconstruir map clave->caso_id actual
        uf2 = _puente_global(filas, uf2, vecs_por_clave, claves, umbral)
        _remap_ids(filas, uf2)
        if verbose:
            n2 = len({f["caso_id"] for f in filas})
            print(f"Tras puente global (umbral {umbral}): {n2} caso_id", flush=True)
        if not _cenepa_ok(filas):
            if verbose:
                print(
                    "AVISO: el puente global fusionó Afrodita/Dorato (Cenepa); "
                    "se revierte. Queda solo el merge de claves idénticas.",
                    flush=True,
                )
            for f, cid in zip(filas, ids_antes_puente):
                f["caso_id"] = cid

    for f in filas:
        f.pop("_clave", None)
        f.pop("_dept", None)
    return filas
