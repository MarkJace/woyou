"""SQLite 数据层：设置、搜索缓存、数据源健康。"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_cache (
    query      TEXT PRIMARY KEY,
    result     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
    source_id  TEXT PRIMARY KEY,
    ok         INTEGER NOT NULL,
    latency_ms REAL,
    checked_at TEXT NOT NULL,
    error      TEXT
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lat        REAL NOT NULL,
    lon        REAL NOT NULL,
    zoom       REAL NOT NULL DEFAULT 8,
    title      TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lat        REAL NOT NULL,
    lon        REAL NOT NULL,
    zoom       REAL NOT NULL DEFAULT 8,
    visited_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _init(self) -> None:
        with _connect(self.path) as conn:
            conn.executescript(_SCHEMA)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    # ---- settings -----------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        with _connect(self.path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock, _connect(self.path) as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, payload),
            )

    # ---- search cache -------------------------------------------------
    def cache_search(self, query: str, result: Any) -> None:
        with self._lock, _connect(self.path) as conn:
            conn.execute(
                "INSERT INTO search_cache(query, result, created_at) VALUES(?, ?, ?) "
                "ON CONFLICT(query) DO UPDATE SET result=excluded.result, "
                "created_at=excluded.created_at",
                (query, json.dumps(result, ensure_ascii=False), _now()),
            )

    def get_cached_search(self, query: str, max_age_seconds: int = 86400) -> Any | None:
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT result, created_at FROM search_cache WHERE query=?", (query,)
            ).fetchone()
        if row is None:
            return None
        try:
            created = datetime.fromisoformat(row["created_at"])
        except ValueError:
            return None
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > max_age_seconds:
            return None
        try:
            return json.loads(row["result"])
        except (TypeError, ValueError):
            return None

    # ---- source health ------------------------------------------------
    def upsert_health(
        self, source_id: str, ok: bool, latency_ms: float | None, error: str | None = None
    ) -> None:
        with self._lock, _connect(self.path) as conn:
            conn.execute(
                "INSERT INTO source_health(source_id, ok, latency_ms, checked_at, error) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(source_id) DO UPDATE SET ok=excluded.ok, "
                "latency_ms=excluded.latency_ms, checked_at=excluded.checked_at, "
                "error=excluded.error",
                (source_id, int(ok), latency_ms, _now(), error),
            )

    def list_health(self) -> list[dict[str, Any]]:
        with _connect(self.path) as conn:
            rows = conn.execute("SELECT * FROM source_health").fetchall()
        return [dict(row) for row in rows]
