# Asistente

Proyecto local de Johao (Universidad del Pacífico): reportes mensuales de conflictos de la Defensoría del Pueblo, de PDF a panel caso × mes.

Si clonaste el repo, empieza por **README.md** (instalar, usar el panel, extraer de nuevo). Esto es el mapa de carpetas.

En la raíz solo hay estas carpetas, en el orden en que conviene leerlas.

| Carpeta | Para qué |
|---|---|
| `01_datos` | Crudos (PDF), inventario y tablas ya extraídas |
| `02_codigo` | Scripts. El de trabajo diario es `extraer_conflictos.py` |
| `03_notas` | Informes LaTeX de la carpeta Minería en Drive (no son el paper) |
| `04_docs` | Cómo funciona el extractor local y por qué se dejó el de Drive |
| `99_archivo` | Descarga vieja, respaldos, sondas de auditoría. No usar para análisis |

Cada carpeta numerada tiene un `INDICE.txt`.

## Datos

- **PDF vigentes:** `01_datos/crudos/pdfs` (mensuales n.º 1–269; no hay junio 2005)
- **Por formato de maqueta:** `01_datos/crudos/pdfs_por_formato` (hardlinks, no son copias extra)
- **Catálogos:** `01_datos/inventario` (`fechas.csv` + `formatos_pdf_defensoria.csv`)
- **Panel:** `01_datos/procesados/conflictos/panel_caso_mes.csv.gz` (en GitHub)  
  Localmente puede estar también el `.csv` sin comprimir. Una fila = un caso en un mes. Minería: `es_socioambiental=1` y/o `menciona_mineria=1`.
- **Calidad:** `01_datos/procesados/conflictos/calidad` (comparaciones, muestra dorada)

`99_archivo/descarga_web_parcial` es el dump viejo (~218 PDF). El corpus unificado está en `crudos/pdfs`.

## Instalar

```text
pip install -r requirements.txt
```

## Extraer de nuevo

```text
python -u 02_codigo/extraer_conflictos.py
```

Agrupa las filas en casos por similitud semántica (embeddings, umbral 0.90). Para volver al método anterior de rapidfuzz: `--identidad fuzzy`. La primera corrida descarga el modelo de embeddings (~120 MB) desde Hugging Face.

Rutas centralizadas en `02_codigo/rutas.py`. No hace falta iLovePDF.

## Control de calidad

| Script | Para qué |
|---|---|
| `comparar_identidad.py` | Contrasta fuzzy contra embeddings a varios umbrales y lista las fusiones más grandes para revisarlas a mano |
| `generar_muestra_dorada.py` | Muestra estratificada por maqueta, a anotar en `calidad/muestra_dorada.xlsx` |
| `evaluar_extraccion.py` | Lee la muestra anotada y reporta precisión por campo y por formato |

## Resúmenes con Gemini (capa aditiva)

No toca la extracción. Lee el panel, llama a Gemini **una vez por caso** y escribe `01_datos/procesados/conflictos/resumenes_llm.csv`.

Autenticación: Vertex AI del proyecto `researchassistant01`, con las credenciales de `gcloud auth application-default login`. Si el sistema tiene `GOOGLE_APPLICATION_CREDENTIALS` de otro proyecto, el script la ignora.

```text
python -u 02_codigo/enriquecer_llm.py --limite 8
python -u 02_codigo/enriquecer_llm.py --solo-mineria
python -u 02_codigo/enriquecer_llm.py
```

La caché queda en `cache_llm.sqlite`. Repetir la corrida no vuelve a pagar los casos ya hechos.

El CSV `casos_unicos.csv` conserva el texto original en `caso`. El Excel `casos_unicos_resumen.xlsx` usa el resumen de Gemini como columna `caso`.

La carpeta **Minería** del Shared Drive `Johao_asistente` es el archivo del grupo; este directorio es el trabajo local de extracción. No toca la otra copia “shared with me”.
