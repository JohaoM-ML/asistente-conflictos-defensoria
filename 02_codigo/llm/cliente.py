"""Cliente Gemini: API key o Vertex con ADC.

Si GOOGLE_APPLICATION_CREDENTIALS apunta a otro proyecto, pisa el ADC de
`gcloud auth application-default login`. Para Vertex se ignora, salvo que
GEMINI_USAR_SA=1.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from llm.esquema import RESPONSE_SCHEMA, normalizar, vacio
from llm.prompts import SISTEMA

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def cargar_env(ruta: Path | None = None) -> None:
    if load_dotenv is None:
        return
    if ruta and ruta.exists():
        load_dotenv(ruta, override=False)


def _usar_vertex() -> bool:
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        auth = (os.environ.get("GEMINI_AUTH") or "api_key").lower()
        if auth == "api_key":
            return False
    return True


def _preparar_adc() -> None:
    """Quita la cuenta de servicio ajena para que google-genai lea el ADC."""
    if os.environ.get("GEMINI_USAR_SA") == "1":
        return
    sa = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or ""
    if not sa:
        return
    proyecto = (
        os.environ.get("GEMINI_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or ""
    )
    try:
        import json as _json

        data = _json.loads(Path(sa).read_text(encoding="utf-8"))
    except Exception:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        return
    if data.get("project_id") and data.get("project_id") != proyecto:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)


def crear_cliente():
    from google import genai

    if _usar_vertex():
        _preparar_adc()
        proyecto = (
            os.environ.get("GEMINI_PROJECT")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
        if not proyecto:
            raise RuntimeError(
                "Falta GEMINI_PROJECT (o GOOGLE_CLOUD_PROJECT) en el entorno/.env. "
                "Ver .env.ejemplo"
            )
        ubicacion = os.environ.get("GEMINI_LOCATION") or "us-central1"
        return genai.Client(vertexai=True, project=proyecto, location=ubicacion)
    clave = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not clave:
        raise RuntimeError(
            "Falta autenticación. Opciones: "
            "1) gcloud auth application-default login + GEMINI_PROJECT (Vertex) "
            "2) GEMINI_API_KEY en el .env"
        )
    return genai.Client(api_key=clave)


def modelo_nombre() -> str:
    return os.environ.get("GEMINI_MODELO") or "gemini-2.5-flash"


def llamar(cliente, texto_usuario: str, max_intentos: int = 6) -> dict:
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=SISTEMA,
        temperature=0.2,
        max_output_tokens=1024,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    espera = 2.0
    ultimo = None
    for _ in range(max_intentos):
        try:
            resp = cliente.models.generate_content(
                model=modelo_nombre(),
                contents=texto_usuario,
                config=config,
            )
            bruto = (resp.text or "").strip()
            if not bruto:
                return vacio()
            try:
                obj = json.loads(bruto)
            except json.JSONDecodeError:
                limpio = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", bruto)
                obj = json.loads(limpio)
            return normalizar(obj)
        except Exception as exc:  # noqa: BLE001 — reintento acotado a 429/503
            ultimo = exc
            msg = str(exc)
            codigo = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if codigo not in {429, 503, 500} and "RESOURCE_EXHAUSTED" not in msg and "429" not in msg:
                raise
            time.sleep(espera)
            espera = min(espera * 2, 60)
    raise RuntimeError(f"Gemini agotó reintentos: {ultimo}")
