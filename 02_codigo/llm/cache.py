"""Caché SQLite: misma entrada + mismo prompt + mismo modelo = no se vuelve a pagar."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class CacheLLM:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                hash TEXT PRIMARY KEY,
                json TEXT NOT NULL,
                modelo TEXT,
                prompt_version TEXT,
                ts TEXT
            )
            """
        )
        self.con.commit()

    def get(self, clave: str) -> dict | None:
        with self._lock:
            row = self.con.execute(
                "SELECT json FROM cache WHERE hash = ?", (clave,)
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def put(self, clave: str, obj: dict, modelo: str, prompt_version: str) -> None:
        with self._lock:
            self.con.execute(
                """
                INSERT OR REPLACE INTO cache (hash, json, modelo, prompt_version, ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    clave,
                    json.dumps(obj, ensure_ascii=False),
                    modelo,
                    prompt_version,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            self.con.commit()

    def close(self) -> None:
        self.con.close()
