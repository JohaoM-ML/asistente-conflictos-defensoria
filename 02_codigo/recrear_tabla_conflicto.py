# -*- coding: utf-8 -*-
"""Recrea la tabla 'Copia de Conflicto (1)' de Drive a partir del panel local."""
from __future__ import annotations

import ast
import calendar
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from defensoria_extract.identidad import estandarizar
from defensoria_extract.layout import fold
from rutas import (
    COMPARACION_DRIVE,
    CONFLICTO_RECREADO_CSV,
    CONFLICTO_RECREADO_XLSX,
    RESUMENES_LLM,
    ruta_panel,
)

DRIVE_XLSX = ROOT.parent / "99_archivo" / "tmp_drive" / "Copia de Conflicto (1).xlsx"
PUEBLOS_XLSX = ROOT.parent / "99_archivo" / "tmp_drive" / "Pueblos de conflictos en minas.xlsx"
PANEL = None  # se resuelve en main() (csv o gz)
SALIDA_XLSX = CONFLICTO_RECREADO_XLSX
SALIDA_CSV = CONFLICTO_RECREADO_CSV
SALIDA_REP = COMPARACION_DRIVE
EXCEL_MAX = 32767

# Catalogo alineado a Casos_Filtrados + valores reales de Copia de Conflicto (1).
CATALOGO = [
    {
        "mina": "Yanacocha",
        "compania": "Newmont",
        "aliases": (
            "yanacocha",
            "quilish",
            "choropampa",
            "minera yanacocha",
        ),
    },
    {
        "mina": "Cerro Corona",
        "compania": "Gold Fields",
        "aliases": (
            "cerro corona",
            "gold fields",
            "goldfields",
            "gold fields la cima",
            "la cima s.a",
            "la cima sa",
        ),
    },
    {
        "mina": "Antamina",
        "compania": "Antamina",
        "aliases": ("antamina",),
    },
    {
        "mina": "Las Bambas",
        "compania": "Las Bambas",
        "aliases": (
            "las bambas",
            "bambas",
            "mmg",
            "challhuahuacho",
            "fuerabamba",
            "fuerabamba",
        ),
    },
    {
        "mina": "Antapaccay",
        "compania": "Antapaccay",
        "aliases": (
            "antapaccay",
            "tintaya",
            "xstrata",
        ),
    },
    {
        "mina": "Toromocho",
        "compania": "Chinalco",
        "aliases": ("toromocho", "chinalco", "morococha"),
    },
    {
        "mina": "Quellaveco",
        "compania": "Angloamerican",
        "aliases": ("quellaveco", "anglo american", "angloamerican"),
    },
    {
        "mina": "Atacocha",
        "compania": "Nexa Resources",
        "aliases": ("atacocha", "milpo"),
    },
    {
        "mina": "Chungar",
        "compania": "Volcan",
        "aliases": ("chungar", "animon", "animón"),
    },
    {
        "mina": "Pucamarca",
        "compania": "Minsur",
        "aliases": ("pucamarca",),
    },
    {
        "mina": "Pierina",
        "compania": "Barrick",
        "aliases": ("pierina", "misquichilca"),
    },
    {
        "mina": "San Nicolas",
        "compania": "San Nicolas",
        "aliases": ("san nicolas", "san nicolás"),
    },
    {
        "mina": "Toquepala",
        "compania": "Southern",
        "aliases": ("toquepala",),
    },
    {
        "mina": "Cuajone",
        "compania": "Southern",
        "aliases": ("cuajone",),
    },
    {
        "mina": "Shougang",
        "compania": "Shougang",
        "aliases": ("shougang", "hierro peru", "hierro perú"),
    },
]

_ALIAS_COMPILED = [
    (
        item,
        re.compile("|".join(rf"\b{re.escape(fold(a))}\b" for a in item["aliases"])),
    )
    for item in CATALOGO
]
_TODOS_ALIAS = re.compile(
    "|".join(rf"\b{re.escape(fold(a))}\b" for item in CATALOGO for a in item["aliases"])
)


def month_end(anio, mes) -> str:
    try:
        y, m = int(anio), int(mes)
        d = calendar.monthrange(y, m)[1]
        return f"{y:04d}-{m:02d}-{d:02d}"
    except (TypeError, ValueError):
        return ""


def hallar_minas(blob: str) -> tuple[list[str], list[str]]:
    minas, comps = [], []
    for item, cre in _ALIAS_COMPILED:
        if cre.search(blob):
            minas.append(item["mina"])
            if item["compania"] not in comps:
                comps.append(item["compania"])
    if "glencore" in blob and "Glencore" not in comps:
        if "Antapaccay" in minas or "Las Bambas" in minas:
            comps.append("Glencore")
    return minas, comps


def tipo_estandar(tipo: str) -> str:
    t = fold(tipo)
    if not t:
        return ""
    if t.startswith("conflictos activos") or t.startswith("detalle"):
        return ""
    if "socioambiental" in t or "socio ambiental" in t:
        return "SOCIOAMBIENTAL"
    if "laboral" in t:
        return "LABORAL"
    if "gobierno local" in t:
        return "GOBIERNO LOCAL"
    if "gobierno regional" in t:
        return "GOBIERNO REGIONAL"
    if "gobierno nacional" in t:
        return "GOBIERNO NACIONAL"
    if "demarcacion" in t:
        return "DEMARCACION TERRITORIAL"
    if "comunal" in t:
        return "COMUNAL"
    if "electoral" in t:
        return "ELECTORAL"
    if "coca" in t:
        return "CULTIVO ILEGAL DE COCA"
    if "otro" in t:
        return "OTROS"
    return fold(tipo).upper()[:40]


def es_ilegal_informal(blob: str) -> tuple[str, str]:
    ilegal = "Sí" if re.search(
        r"\b(mineria ilegal|minero ilegal|mineros ilegales|extraccion ilegal|ilegal)\b",
        blob,
    ) else "No"
    informal = "Sí" if re.search(
        r"\b(informal|informales|mineria informal|minero informal)\b", blob
    ) else "No"
    return ilegal, informal


def cargar_resumenes_llm() -> dict[str, str]:
    if not RESUMENES_LLM.exists():
        return {}
    df = pd.read_csv(RESUMENES_LLM, dtype=str, keep_default_na=False)
    if "caso_id" not in df.columns or "resumen" not in df.columns:
        return {}
    out = {}
    for _, r in df.iterrows():
        texto = str(r.get("resumen") or "").strip()
        if texto:
            out[str(r["caso_id"])] = texto
    return out


def resumen_extractivo(texto: str, limite: int = 420) -> str:
    t = re.sub(r"\s+", " ", (texto or "")).strip(" .;")
    if not t:
        return ""
    partes = re.split(r"(?<=[.!?])\s+", t)
    acc = []
    for p in partes:
        acc.append(p)
        if len(" ".join(acc)) >= 180:
            break
    s = " ".join(acc).strip()
    return s[:limite]


def dept_clave(d: str) -> str:
    t = fold(d).upper().replace("Á", "A")
    t = re.sub(r"[^A-Z ]", "", fold(d).upper())
    t = t.replace("ANCASH", "ANCASH").replace("APURIMAC", "APURIMAC")
    return re.sub(r"\s+", " ", t).strip()


def fmt_lista(xs: list[str]) -> str:
    if not xs:
        return ""
    return str(xs)


def pick_longest(series: pd.Series) -> str:
    vals = [str(v).strip() for v in series.tolist() if str(v).strip() and str(v).lower() != "nan"]
    if not vals:
        return ""
    return max(vals, key=len)


def cargar_pueblos() -> dict[str, list[tuple[str, str]]]:
    if not PUEBLOS_XLSX.exists():
        return {}
    df = pd.read_excel(PUEBLOS_XLSX, sheet_name="Listado_Pueblos")
    por: dict[str, list[tuple[str, str]]] = {}
    vistos: dict[str, set[str]] = {}
    for _, r in df.iterrows():
        mina = str(r.get("MINA") or "").split(",")[0].strip()
        if not mina:
            continue
        por.setdefault(mina, [])
        vistos.setdefault(mina, set())
        for col in ("CENTRO_POBLADO", "LUGAR_REFERIDO"):
            n = str(r.get(col) or "").strip()
            nf = fold(n)
            if len(nf) < 6 or n in vistos[mina]:
                continue
            vistos[mina].add(n)
            por[mina].append((n, nf))
    for mina in por:
        por[mina].sort(key=lambda x: -len(x[1]))
        por[mina] = por[mina][:120]
    return por


def pueblos_de(blob: str, minas: list[str], catalogo: dict[str, list[tuple[str, str]]], ubicacion: str) -> str:
    hallados = []
    for mina in minas:
        for nom, nf in catalogo.get(mina, []):
            if nf in blob and nom not in hallados:
                hallados.append(nom)
            if len(hallados) >= 6:
                break
        if len(hallados) >= 6:
            break
    if hallados:
        return "; ".join(hallados[:6])
    ub = re.sub(r"\s+", " ", ubicacion or "").strip()
    return ub[:220]


def parse_drive_list(x) -> list[str]:
    if pd.isna(x):
        return []
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return []
    found = re.findall(r"'([^']*)'", s)
    found = [f.strip() for f in found if f.strip()]
    if found:
        return found
    try:
        v = ast.literal_eval(s)
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, list):
                    out.extend(str(i).strip() for i in item if str(i).strip())
                elif str(item).strip():
                    out.append(str(item).strip())
            return out
    except Exception:
        pass
    return [s]


def trunc_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].apply(
                lambda x: x[:EXCEL_MAX] if isinstance(x, str) and len(x) > EXCEL_MAX else x
            )
    return out


def construir_tabla(panel: pd.DataFrame, pueblos_cat: dict, resumenes_llm: dict[str, str] | None = None) -> pd.DataFrame:
    panel = panel.copy()
    cols_corto = [
        "tipo",
        "caso",
        "ubicacion",
        "actores_primarios",
        "actores_secundarios",
        "actores_terciarios",
        "actores",
    ]
    panel["_blob"] = (
        panel[cols_corto].fillna("").astype(str).agg(" ".join, axis=1).map(fold)
    )
    mask = panel["_blob"].str.contains(_TODOS_ALIAS.pattern, regex=True, na=False)
    panel = panel[mask].copy()
    panel["_minas"] = panel["_blob"].map(lambda b: hallar_minas(b)[0])
    panel = panel[panel["_minas"].map(bool)].copy()
    filas = []
    for cid, g in panel.groupby("caso_id", sort=False):
        blob = fold(" ".join(g["_blob"].tolist()))
        minas, comps = hallar_minas(blob)
        if not minas:
            # union de filas
            for lst in g["_minas"]:
                for m in lst:
                    if m not in minas:
                        minas.append(m)
            _, comps = hallar_minas(blob)
            for item in CATALOGO:
                if item["mina"] in minas and item["compania"] not in comps:
                    comps.append(item["compania"])
        ilegal, informal = es_ilegal_informal(blob)
        tipos = [tipo_estandar(t) for t in g["tipo"].fillna("").astype(str)]
        tipos = [t for t in tipos if t]
        tipo = Counter(tipos).most_common(1)[0][0] if tipos else ""
        depts = [str(d).strip() for d in g["departamento"].fillna("") if str(d).strip()]
        dept = Counter(depts).most_common(1)[0][0] if depts else ""
        caso = pick_longest(g["caso"])
        llm = (resumenes_llm or {}).get(str(cid), "")
        if llm:
            resumen, fuente = llm, "gemini"
        else:
            resumen, fuente = resumen_extractivo(caso), "extractivo_caso (no ChatGPT)"
        actores_p = pick_longest(g["actores_primarios"])
        actores_s = pick_longest(g["actores_secundarios"])
        actores_t = pick_longest(g["actores_terciarios"])
        actores = pick_longest(g["actores"])
        ubic = pick_longest(g["ubicacion"])
        fechas = []
        for _, r in g.iterrows():
            fe = month_end(r.get("anio"), r.get("mes"))
            if fe:
                fechas.append(fe)
        fechas.sort()
        socio = int((g["es_socioambiental"].fillna("0").astype(str) == "1").any())
        menc = int((g["menciona_mineria"].fillna("0").astype(str) == "1").any())
        completo = int(bool(caso) and bool(tipo or actores_p or actores) and bool(minas))
        gid = f"Caso_{cid}"
        filas.append(
            {
                "Grupo": gid,
                "CasoResumidoChatGPT": resumen,
                "EsMinera": "Sí",
                "EsIlegal": ilegal,
                "EsInformal": informal,
                "Pueblos": pueblos_de(blob, minas, pueblos_cat, ubic),
                "Minas": fmt_lista(minas),
                "Compañía minera": fmt_lista(comps),
                "Completo": completo,
                "PrimeraFecha_min": fechas[0] if fechas else "",
                "UltimaFecha_max": fechas[-1] if fechas else "",
                "GrupoID": gid,
                "Departamento": dept.upper() if dept else "",
                "Tipo_estandarizado": tipo,
                "Caso": caso,
                "Actores": actores,
                "Actores primarios": actores_p,
                "Actores secundarios": actores_s,
                "Actores terciarios": actores_t,
                "caso_id": cid,
                "n_meses": int(g[["anio", "mes"]].drop_duplicates().shape[0]),
                "n_filas_panel": len(g),
                "numero_reporte_min": pd.to_numeric(g["numero_reporte"], errors="coerce").min(),
                "numero_reporte_max": pd.to_numeric(g["numero_reporte"], errors="coerce").max(),
                "es_socioambiental": socio,
                "menciona_mineria": menc,
                "ubicacion": ubic,
                "fuente_resumen": fuente,
                "caso_estandarizado": estandarizar(caso),
            }
        )
    out = pd.DataFrame(filas)
    out = out.sort_values(["Departamento", "Minas", "PrimeraFecha_min", "Grupo"]).reset_index(drop=True)
    return out


def col_compania(df: pd.DataFrame) -> str:
    for c in df.columns:
        fc = fold(c).replace(" ", "")
        if "compan" in fc:
            return c
    for c in df.columns:
        if c != "EsMinera" and "minera" in fold(c):
            return c
    return df.columns[7]


def comparar(ours: pd.DataFrame, drive: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    cc = col_compania(drive)
    drive = drive.copy()
    drive["_caso_e"] = drive["Caso"].map(lambda x: estandarizar(str(x)))
    drive["_dept"] = drive["Departamento"].map(dept_clave)
    drive["_minas"] = drive["Minas"].map(parse_drive_list)
    drive["_comp"] = drive[cc].map(parse_drive_list)
    ours = ours.copy()
    ours["_caso_e"] = ours["caso_estandarizado"].fillna("").astype(str)
    ours["_dept"] = ours["Departamento"].map(dept_clave)
    ours["_minas"] = ours["Minas"].map(parse_drive_list)
    ours["_comp"] = ours["Compañía minera"].map(parse_drive_list)

    por_dept: dict[str, list] = {}
    for j, o in ours.iterrows():
        por_dept.setdefault(o["_dept"], []).append(j)
        por_dept.setdefault("_ALL_", []).append(j)

    usados = set()
    pares = []
    for i, d in drive.iterrows():
        best = None
        best_sc = -1
        best_j = None
        candidatos = por_dept.get(d["_dept"] or "", [])
        extra = [j for j in por_dept["_ALL_"] if j not in candidatos]
        for j in list(candidatos) + extra:
            if j in usados:
                continue
            o = ours.loc[j]
            sc_txt = fuzz.token_sort_ratio(d["_caso_e"], o["_caso_e"]) if d["_caso_e"] and o["_caso_e"] else 0
            sc_dept = 100.0 if d["_dept"] and d["_dept"] == o["_dept"] else 0.0
            inter = set(d["_minas"]) & set(o["_minas"])
            sc_mina = 100.0 if inter else (40.0 if d["_minas"] and o["_minas"] else 0.0)
            score = 0.62 * sc_txt + 0.20 * sc_dept + 0.18 * sc_mina
            if score > best_sc:
                best_sc = score
                best = (sc_txt, sc_dept, sc_mina, inter)
                best_j = j
            if sc_txt >= 96 and sc_dept == 100:
                break
        if best_j is None or best_sc < 70:
            pares.append(
                {
                    "Grupo_drive": d["GrupoID"],
                    "Departamento_drive": d["Departamento"],
                    "Minas_drive": d["Minas"],
                    "Caso_drive": str(d["Caso"])[:240],
                    "Grupo_local": "",
                    "score": round(best_sc, 1) if best_j is not None else 0,
                    "match": 0,
                    "dept_ok": 0,
                    "tipo_ok": 0,
                    "mina_ok": 0,
                    "compania_ok": 0,
                    "fecha_ok": 0,
                }
            )
            continue
        usados.add(best_j)
        o = ours.loc[best_j]
        tipo_d = str(d.get("Tipo_estandarizado") or "").strip().upper()
        tipo_o = str(o.get("Tipo_estandarizado") or "").strip().upper()
        tipo_ok = int(bool(tipo_d) and tipo_d == tipo_o)
        mina_ok = int(bool(set(d["_minas"]) & set(o["_minas"])))
        comp_ok = int(bool(set(d["_comp"]) & set(o["_comp"])))
        dept_ok = int(d["_dept"] == o["_dept"])
        try:
            fd = str(d["PrimeraFecha_min"])[:7]
            fo = str(o["PrimeraFecha_min"])[:7]
            # diferencia en meses
            y1, m1 = int(fd[:4]), int(fd[5:7])
            y2, m2 = int(fo[:4]), int(fo[5:7])
            delta = abs((y1 * 12 + m1) - (y2 * 12 + m2))
            fecha_ok = int(delta <= 6)
        except Exception:
            fecha_ok = 0
        pares.append(
            {
                "Grupo_drive": d["GrupoID"],
                "Departamento_drive": d["Departamento"],
                "Minas_drive": d["Minas"],
                "Caso_drive": str(d["Caso"])[:240],
                "Grupo_local": o["GrupoID"],
                "Departamento_local": o["Departamento"],
                "Minas_local": o["Minas"],
                "Caso_local": str(o["Caso"])[:240],
                "score": round(best_sc, 1),
                "score_texto": round(best[0], 1),
                "match": 1,
                "dept_ok": dept_ok,
                "tipo_ok": tipo_ok,
                "mina_ok": mina_ok,
                "compania_ok": comp_ok,
                "fecha_ok": fecha_ok,
                "Tipo_drive": tipo_d,
                "Tipo_local": tipo_o,
                "PrimeraFecha_drive": d["PrimeraFecha_min"],
                "PrimeraFecha_local": o["PrimeraFecha_min"],
                "UltimaFecha_drive": d["UltimaFecha_max"],
                "UltimaFecha_local": o["UltimaFecha_max"],
            }
        )
    cmp = pd.DataFrame(pares)
    n_d = len(drive)
    n_m = int(cmp["match"].sum())
    m = cmp[cmp["match"] == 1]
    stats = {
        "n_drive": n_d,
        "n_local": len(ours),
        "n_emparejados": n_m,
        "recall": 100.0 * n_m / n_d if n_d else 0,
        "precision_vs_drive": 100.0 * n_m / len(ours) if len(ours) else 0,
        "dept_ok": 100.0 * m["dept_ok"].mean() if n_m else 0,
        "tipo_ok": 100.0 * m["tipo_ok"].mean() if n_m else 0,
        "mina_ok": 100.0 * m["mina_ok"].mean() if n_m else 0,
        "compania_ok": 100.0 * m["compania_ok"].mean() if n_m else 0,
        "fecha_ok": 100.0 * m["fecha_ok"].mean() if n_m else 0,
        "score_medio": float(m["score"].mean()) if n_m else 0,
    }
    # exactitud global: recall ponderado con acuerdo de campos en emparejados
    if n_m:
        acuerdo = (
            0.25 * stats["dept_ok"]
            + 0.20 * stats["tipo_ok"]
            + 0.30 * stats["mina_ok"]
            + 0.15 * stats["compania_ok"]
            + 0.10 * stats["fecha_ok"]
        )
        stats["exactitud_emparejados"] = acuerdo
        stats["exactitud_global"] = 0.55 * stats["recall"] + 0.45 * acuerdo
    else:
        stats["exactitud_emparejados"] = 0
        stats["exactitud_global"] = 0
    return cmp, stats


def main() -> None:
    global PANEL
    PANEL = ruta_panel()
    print("Leyendo panel...", flush=True)
    cols = [
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
        "es_socioambiental",
        "menciona_mineria",
    ]
    panel = pd.read_csv(
        PANEL, dtype=str, encoding="utf-8", keep_default_na=False, usecols=cols
    )
    print("  filas", len(panel), flush=True)
    pueblos_cat = cargar_pueblos()
    print("Construyendo tabla estilo Conflicto...", flush=True)
    resumenes_llm = cargar_resumenes_llm()
    if resumenes_llm:
        print(f"  resúmenes Gemini disponibles: {len(resumenes_llm)}", flush=True)
    ours = construir_tabla(panel, pueblos_cat, resumenes_llm)
    print("  casos mineros catalogo Drive", len(ours), flush=True)
    drive = pd.read_excel(DRIVE_XLSX)
    print("Comparando con Drive...", flush=True)
    cmp, stats = comparar(ours, drive)

    campos_drive = [
        "Grupo",
        "CasoResumidoChatGPT",
        "EsMinera",
        "EsIlegal",
        "EsInformal",
        "Pueblos",
        "Minas",
        "Compañía minera",
        "Completo",
        "PrimeraFecha_min",
        "UltimaFecha_max",
        "GrupoID",
        "Departamento",
        "Tipo_estandarizado",
        "Caso",
        "Actores",
        "Actores primarios",
        "Actores secundarios",
        "Actores terciarios",
    ]
    extras = [c for c in ours.columns if c not in campos_drive]
    orden = campos_drive + extras

    ours_x = trunc_df(ours[orden])
    SALIDA_XLSX.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(SALIDA_XLSX, engine="openpyxl") as w:
        ours_x.to_excel(w, sheet_name="Conflicto", index=False)
        trunc_df(cmp).to_excel(w, sheet_name="Comparacion_Drive", index=False)
        pd.DataFrame([stats]).to_excel(w, sheet_name="Exactitud", index=False)
    ours_x.to_csv(SALIDA_CSV, index=False, encoding="utf-8-sig")

    lineas = [
        "COMPARACIÓN: Copia de Conflicto (1) [Drive] vs conflicto_recreado [local]",
        "",
        f"Filas Drive: {stats['n_drive']}",
        f"Filas locales (mismo catálogo de minas): {stats['n_local']}",
        f"Emparejados (score >= 70, greedy 1-1): {stats['n_emparejados']}",
        "",
        f"Recuperación (recall, % de los 83 de Drive hallados): {stats['recall']:.1f}%",
        f"Precisión vs Drive (% de filas locales que coinciden con un caso Drive): {stats['precision_vs_drive']:.1f}%",
        f"Score medio de emparejamiento: {stats['score_medio']:.1f}",
        "",
        "Acuerdo de campos SOLO entre emparejados:",
        f"  Departamento: {stats['dept_ok']:.1f}%",
        f"  Tipo_estandarizado: {stats['tipo_ok']:.1f}%",
        f"  Minas (al menos una en común): {stats['mina_ok']:.1f}%",
        f"  Compañía (al menos una en común): {stats['compania_ok']:.1f}%",
        f"  Primera fecha (±6 meses): {stats['fecha_ok']:.1f}%",
        f"  Exactitud de campos (ponderada): {stats['exactitud_emparejados']:.1f}%",
        "",
        f"EXACTITUD GLOBAL (0.55*recall + 0.45*acuerdo de campos): {stats['exactitud_global']:.1f}%",
        "",
        "Notas:",
        "- El resumen es Gemini si existe resumenes_llm.csv; si no, extractivo del campo Caso (fuente_resumen).",
        "- Pueblos: cruce con el listado de Drive si el nombre aparece en el texto; si no, ubicación extraída.",
        "- EsIlegal/EsInformal: heurística de palabras, no la etiqueta manual de Drive.",
        "- Hay más filas locales porque hay más PDF (hasta n.269) y el agrupamiento fuzzy es distinto.",
        "- CasoResumidoChatGPT de Drive no se puede reproducir al pie de la letra sin el modelo original.",
        "",
        f"Salida: {SALIDA_XLSX}",
    ]
    SALIDA_REP.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
