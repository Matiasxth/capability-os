"""SQLite-vec backed vector store — drop-in replacement for VectorStore.

Uses the sqlite-vec extension for hardware-accelerated vector search.
Falls back gracefully if sqlite-vec is not installed.

Same public API as VectorStore: add, delete, search, count, clear, get.
"""
from __future__ import annotations

import json
import sqlite3
import struct
import threading
from pathlib import Path
from threading import RLock
from typing import Any


def _serialize_f32(vec: list[float]) -> bytes:
    """Pack a float list into little-endian f32 bytes for sqlite-vec."""
    return struct.pack(f"<{len(vec)}f", *vec)


class SqliteVectorStore:
    """Thread-safe vector store using SQLite + sqlite-vec extension."""

    def __init__(self, data_path: str | Path, dimensions: int = 0) -> None:
        self._path = str(Path(data_path).resolve())
        self._lock = RLock()
        self._dims = dimensions
        self._conn: sqlite3.Connection | None = None
        self._local = threading.local()  # thread-local connections for safe reads
        self._init_db()

    def _get_read_conn(self) -> sqlite3.Connection:
        """Get a thread-local read-only connection for safe concurrent reads."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=True)
            try:
                import sqlite_vec
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except Exception:
                pass
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        try:
            import sqlite_vec
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS vec_meta (
                    id TEXT PRIMARY KEY,
                    metadata TEXT
                )
            """)
            self._conn.commit()
            self._vec_table_ready = False
        except Exception:
            self._conn = None

    def _ensure_vec_table(self, dims: int) -> None:
        """Create the virtual vec table once we know the dimensionality."""
        if self._vec_table_ready or self._conn is None:
            return
        self._dims = dims
        try:
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_data
                USING vec0(embedding float[{dims}])
            """)
            self._conn.commit()
            self._vec_table_ready = True
        except Exception:
            pass

    @property
    def available(self) -> bool:
        return self._conn is not None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, entry_id: str, vector: list[float], metadata: dict[str, Any] | None = None) -> None:
        with self._lock:
            if self._conn is None:
                return
            dims = len(vector)
            self._ensure_vec_table(dims)
            try:
                # Get next rowid
                row = self._conn.execute("SELECT MAX(rowid) FROM vec_data").fetchone()
                rowid = (row[0] or 0) + 1

                self._conn.execute(
                    "INSERT INTO vec_data(rowid, embedding) VALUES (?, ?)",
                    (rowid, _serialize_f32(vector)),
                )
                meta = json.dumps({**(metadata or {}), "_vec_rowid": rowid}, ensure_ascii=False)
                self._conn.execute(
                    "INSERT OR REPLACE INTO vec_meta(id, metadata) VALUES (?, ?)",
                    (entry_id, meta),
                )
                self._conn.commit()
            except Exception:
                pass

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            if self._conn is None:
                return False
            try:
                row = self._conn.execute(
                    "SELECT metadata FROM vec_meta WHERE id = ?", (entry_id,)
                ).fetchone()
                if row is None:
                    return False
                meta = json.loads(row[0])
                rowid = meta.get("_vec_rowid")
                if rowid:
                    self._conn.execute("DELETE FROM vec_data WHERE rowid = ?", (rowid,))
                self._conn.execute("DELETE FROM vec_meta WHERE id = ?", (entry_id,))
                self._conn.commit()
                return True
            except Exception:
                return False

    def clear(self) -> None:
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.execute("DELETE FROM vec_meta")
                if self._vec_table_ready:
                    self._conn.execute("DROP TABLE IF EXISTS vec_data")
                    self._vec_table_ready = False
                self._conn.commit()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        with self._lock:
            if self._conn is None or not self._vec_table_ready:
                return []
            try:
                rows = self._conn.execute(
                    """
                    SELECT v.rowid, v.distance
                    FROM vec_data v
                    WHERE v.embedding MATCH ?
                    ORDER BY v.distance
                    LIMIT ?
                    """,
                    (_serialize_f32(query_vector), top_k),
                ).fetchall()

                results: list[dict[str, Any]] = []
                for rowid, distance in rows:
                    meta_row = self._conn.execute(
                        "SELECT id, metadata FROM vec_meta WHERE metadata LIKE ?",
                        (f'%"_vec_rowid": {rowid}%',),
                    ).fetchone()
                    if meta_row:
                        meta = json.loads(meta_row[1])
                        meta.pop("_vec_rowid", None)
                        # Convert distance to similarity score (1 / (1 + distance))
                        score = 1.0 / (1.0 + distance) if distance >= 0 else 0.0
                        results.append({
                            "id": meta_row[0],
                            "score": score,
                            "metadata": meta,
                        })
                return results
            except Exception:
                return []

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            if self._conn is None:
                return None
            try:
                row = self._conn.execute(
                    "SELECT metadata FROM vec_meta WHERE id = ?", (entry_id,)
                ).fetchone()
                if row is None:
                    return None
                meta = json.loads(row[0])
                meta.pop("_vec_rowid", None)
                return {"id": entry_id, "metadata": meta}
            except Exception:
                return None

    def count(self) -> int:
        with self._lock:
            if self._conn is None:
                return 0
            try:
                row = self._conn.execute("SELECT COUNT(*) FROM vec_meta").fetchone()
                return row[0] if row else 0
            except Exception:
                return 0
