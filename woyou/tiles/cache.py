"""基于 MBTiles 的瓦片缓存。"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tiles (
    zoom_level   INTEGER NOT NULL,
    tile_column  INTEGER NOT NULL,
    tile_row     INTEGER NOT NULL,
    tile_data    BLOB NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'image/png',
    accessed_at  INTEGER NOT NULL,
    PRIMARY KEY (zoom_level, tile_column, tile_row)
);
CREATE INDEX IF NOT EXISTS idx_tiles_accessed ON tiles(accessed_at);
CREATE TABLE IF NOT EXISTS metadata (
    name  TEXT PRIMARY KEY,
    value TEXT
);
"""

_MIME_BY_FORMAT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def _tms_row(z: int, y: int) -> int:
    return (1 << z) - 1 - y


class TileCache:
    """单个数据源的 MBTiles 缓存。"""

    def __init__(self, path: Path, max_bytes: int, name: str = ""):
        self.path = Path(path)
        self.max_bytes = max(64 * 1024 * 1024, int(max_bytes))
        self.name = name or self.path.stem
        self._lock = threading.Lock()
        self._writes = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO metadata(name, value) VALUES('name', ?)", (self.name,)
            )
            conn.execute(
                "INSERT OR IGNORE INTO metadata(name, value) VALUES('format', 'mixed')"
            )

    def get(self, z: int, x: int, y: int) -> tuple[bytes, str] | None:
        row = None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT tile_data, content_type FROM tiles "
                "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, _tms_row(z, y)),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE tiles SET accessed_at=? "
                    "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                    (int(time.time()), z, x, _tms_row(z, y)),
                )
        if row is None:
            return None
        return bytes(row["tile_data"]), row["content_type"] or "image/png"

    def put(self, z: int, x: int, y: int, data: bytes, content_type: str) -> None:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tiles"
                "(zoom_level, tile_column, tile_row, tile_data, content_type, accessed_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (z, x, _tms_row(z, y), data, content_type, now),
            )
            self._writes += 1
        if self._writes % 100 == 0 and self.path.stat().st_size > self.max_bytes:
            self.prune()

    def prune(self) -> None:
        target = int(self.max_bytes * 0.85)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(tile_data)), 0) FROM tiles"
            ).fetchone()
            size = int(row[1]) if row else 0
            while size > target:
                rows = conn.execute(
                    "SELECT rowid, LENGTH(tile_data) FROM tiles "
                    "ORDER BY accessed_at ASC LIMIT 200"
                ).fetchall()
                if not rows:
                    break
                rowids = [r["rowid"] for r in rows]
                freed = sum(int(r[1]) for r in rows)
                conn.executemany("DELETE FROM tiles WHERE rowid=?", [(i,) for i in rowids])
                size -= freed

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(tile_data)), 0) FROM tiles"
            ).fetchone()
        count = int(row[0]) if row else 0
        size = int(row[1]) if row else 0
        return {
            "source": self.name,
            "tiles": count,
            "bytes": size,
            "max_bytes": self.max_bytes,
        }


class CacheManager:
    def __init__(self, root: Path, total_max_bytes: int):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.total_max_bytes = total_max_bytes
        self.per_source_max = max(128 * 1024 * 1024, total_max_bytes // 4)
        self._caches: dict[str, TileCache] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _safe(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.@-]", "_", name)

    def get(self, key: str) -> TileCache:
        safe = self._safe(key)
        with self._lock:
            cache = self._caches.get(safe)
            if cache is None:
                cache = TileCache(self.root / f"{safe}.mbtiles", self.per_source_max, safe)
                self._caches[safe] = cache
            return cache

    def stats(self) -> dict[str, Any]:
        items = [cache.stats() for cache in list(self._caches.values())]
        return {
            "total_bytes": sum(item["bytes"] for item in items),
            "total_tiles": sum(item["tiles"] for item in items),
            "sources": sorted(items, key=lambda item: item["bytes"], reverse=True),
        }
