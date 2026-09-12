# Asistente

De los reportes mensuales de conflictos sociales de la [Defensoría del Pueblo](https://www.defensoria.gob.pe/categorias_de_documentos/reportes/) (Perú) a un **panel caso × mes**.

Proyecto de investigación, Universidad del Pacífico. Una fila del panel es un conflicto en un mes. Para minería: `es_socioambiental=1` y/o `menciona_mineria=1`.

Hay dos maneras de reproducirlo. La A no necesita PDF ni GPU. La B reconstruye el panel desde los PDF públicos.

## Qué hay en el repo (y qué no)

| En GitHub | No se versiona (y por qué) |
|---|---|
| Código, `requirements.txt`, `.env.ejemplo` | `.env` (credenciales) |
| Inventario (`fechas.csv`, `formatos_pdf_defensoria.csv`) | Los PDF (~580 MB). Se bajan o se copian a `01_datos/crudos/pdfs` |
| `panel_caso_mes.csv.gz` (~28 MB) | `panel_caso_mes.csv` sin comprimir (~137 MB; GitHub corta a 100 MB) |
| `casos_unicos.csv`, `RESUMEN.txt`, resúmenes Gemini | `cache_llm.sqlite`, respaldos, primera descarga incompleta |

Los PDF son documentos públicos de la Defensoría. No los subimos para que el clon sea liviano. pandas lee el `.gz` directo.

## Requisitos

- Python **3.11** o **3.12**
- 8 GB de RAM (más si vas a re-extraer con embeddings)
- Internet la primera vez que corras embeddings (modelo ~120 MB desde Hugging Face)

```text
python -m venv .venv
```

Windows:

```text
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```text
source .venv/bin/activate
pip install -r requirements.txt
```

Comprueba el clon:

```text
python -u 02_codigo/comprobar_entorno.py
```

## A. Usar las tablas ya extraídas

No hace falta bajar PDF ni Gemini.

```text
python -c "import sys; sys.path.insert(0,'02_codigo'); import pandas as pd; from rutas import ruta_panel, ENCODING_CSV; df=pd.read_csv(ruta_panel(), dtype=str, encoding=ENCODING_CSV); print(len(df), 'filas')"
```

O abre `02_codigo/leer_panel_caso_mes.ipynb`.

Conteos de referencia de la última extracción (también en `01_datos/procesados/conflictos/RESUMEN.txt`):

- 269 reportes mensuales (n.º 1–269; no hay junio 2005)
- ~41 880 filas caso × mes
- ~2 968 `caso_id` (embeddings, umbral 0.90)

Si quieres el CSV descomprimido (por ejemplo para Excel):

```text
python -c "import gzip,shutil; from pathlib import Path; p=Path('01_datos/procesados/conflictos/panel_caso_mes.csv'); shutil.copyfileobj(gzip.open(p.with_suffix(p.suffix+'.gz'),'rb'), p.open('wb'))"
```

## B. Extraer de nuevo desde los PDF

Los nombres de archivo cambian según de dónde se bajen. Por eso, **después de juntar los PDF hay que regenerar fechas y formatos** (no uses el inventario del repo si tus archivos se llaman distinto).

```text
python -u 02_codigo/descargar_reportes_defensoria.py
python -u 02_codigo/extraer_fechas_reportes.py
python -u 02_codigo/clasificar_formatos_pdf.py
python -u 02_codigo/extraer_conflictos.py
```

Prueba corta (2 PDF):

```text
python -u 02_codigo/extraer_conflictos.py --max 2
```

`descargar_reportes_defensoria.py` recorre las listas públicas de la Defensoría y de gob.pe. No garantiza los 269: los más antiguos a veces solo estaban en copias de archivo. Si te faltan números, pon esos PDF a mano en `01_datos/crudos/pdfs` y vuelve a correr fechas → formatos → extracción.

La primera agrupación por embeddings baja `paraphrase-multilingual-MiniLM-L12-v2`. Para el método viejo (rapidfuzz): `--identidad fuzzy`.

Rutas en `02_codigo/rutas.py`. No hace falta iLovePDF.

`consolidar_pdfs_defensoria.py`, `completar_faltantes_defensoria.py` y `cruzar_pdfs_defensoria.py` son de la máquina original (Google Drive). **No hacen falta para reproducir.**

## C. Resúmenes Gemini (opcional)

No toca la extracción. Lee el panel y escribe `resumenes_llm.csv`.

```text
copy .env.ejemplo .env
```

En macOS/Linux: `cp .env.ejemplo .env`.

Lo más simple en otra máquina es una clave de [Google AI Studio](https://aistudio.google.com/):

```text
GEMINI_AUTH=api_key
GEMINI_API_KEY=...
```

Vertex AI (proyecto propio) está documentado en `.env.ejemplo`. El proyecto `researchassistant01` es solo de este equipo: cámbialo o usa la API key.

```text
python -u 02_codigo/enriquecer_llm.py --limite 8
```

## Control de calidad

```text
python -u 02_codigo/comparar_identidad.py
python -u 02_codigo/generar_muestra_dorada.py
python -u 02_codigo/evaluar_extraccion.py
```

Salidas en `01_datos/procesados/conflictos/calidad`.

## Carpetas

| Carpeta | Para qué |
|---|---|
| `01_datos` | Inventario, panel y (si las bajaste) PDF |
| `02_codigo` | Scripts. Diario: `extraer_conflictos.py` |
| `03_notas` | Informes de la carpeta Minería en Drive |
| `04_docs` | Cómo extrae este directorio y el pipeline viejo |
| `99_archivo` | En el clon solo queda el índice; respaldos y PDF viejos no se suben |

Cada carpeta numerada tiene un `INDICE.txt`. Mapa más corto: `LEEME.md`.

## Licencia y fuente

El código se publica bajo [MIT](LICENSE). Los PDF son de la Defensoría del Pueblo; este repo no los redistribuye. Las tablas extraídas se pueden reutilizar citando la fuente original y este extractor.

La carpeta **Minería** del Shared Drive `Johao_asistente` es el archivo del grupo. Este directorio es el trabajo local de extracción.
