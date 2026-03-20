"""sqlite-vec database: schema init, insert, KNN search.

Uses apsw instead of stdlib sqlite3 because macOS Python is compiled
with OMIT_LOAD_EXTENSION, which blocks sqlite-vec's native extension loading.
"""

from datetime import datetime, timezone
from pathlib import Path

import apsw
import numpy as np
import sqlite_vec


def connect(db_path: Path) -> apsw.Connection:
    """Open connection with sqlite-vec extension loaded."""
    conn = apsw.Connection(str(db_path))
    conn.enable_load_extension(True)
    conn.load_extension(sqlite_vec.loadable_path())
    conn.enable_load_extension(False)
    return conn


_SCHEMA_STMTS = [
    """CREATE TABLE IF NOT EXISTS embedded_assets (
        sha256 TEXT PRIMARY KEY,
        content_type TEXT NOT NULL,
        source_path TEXT NOT NULL,
        manifest_path TEXT,
        embedding_input TEXT NOT NULL,
        dimensions INTEGER NOT NULL,
        embedded_at TEXT NOT NULL,
        api_latency_ms REAL,
        input_tokens INTEGER,
        error TEXT
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS vec_images USING vec0(
        sha256 TEXT PRIMARY KEY,
        embedding float[3072] distance_metric=cosine
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS vec_text USING vec0(
        sha256 TEXT PRIMARY KEY,
        embedding float[3072] distance_metric=cosine
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS vec_documents USING vec0(
        sha256 TEXT PRIMARY KEY,
        embedding float[3072] distance_metric=cosine
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS vec_images_768 USING vec0(
        sha256 TEXT PRIMARY KEY,
        embedding float[768] distance_metric=cosine
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS vec_images_1536 USING vec0(
        sha256 TEXT PRIMARY KEY,
        embedding float[1536] distance_metric=cosine
    )""",
]


def init_db(db_path: Path) -> apsw.Connection:
    """Create schema and return connection."""
    conn = connect(db_path)
    for stmt in _SCHEMA_STMTS:
        conn.execute(stmt)
    return conn


def _serialize(vec: list[float]) -> bytes:
    """Convert float list to bytes for sqlite-vec."""
    return np.array(vec, dtype=np.float32).tobytes()


def _row_to_dict(cursor, row) -> dict:
    """Convert apsw cursor row to dict using description."""
    desc = cursor.getdescription()
    return {d[0]: v for d, v in zip(desc, row)}


def insert_embedding(
    conn: apsw.Connection,
    *,
    sha256: str,
    content_type: str,
    source_path: str,
    manifest_path: str | None,
    embedding_input: str,
    vector: list[float],
    table: str,
    latency_ms: float | None = None,
    input_tokens: int | None = None,
    error: str | None = None,
) -> None:
    """Insert an embedding into both the metadata and vec tables."""
    dims = len(vector)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT OR REPLACE INTO embedded_assets
           (sha256, content_type, source_path, manifest_path,
            embedding_input, dimensions, embedded_at,
            api_latency_ms, input_tokens, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sha256, content_type, source_path, manifest_path,
         embedding_input, dims, now, latency_ms, input_tokens, error),
    )

    conn.execute(
        f"INSERT OR REPLACE INTO {table} (sha256, embedding) VALUES (?, ?)",
        (sha256, _serialize(vector)),
    )


def knn_search(
    conn: apsw.Connection,
    table: str,
    query_vec: list[float],
    k: int = 10,
) -> list[dict]:
    """KNN search returning [{sha256, distance}, ...]."""
    cursor = conn.execute(
        f"""SELECT sha256, distance
            FROM {table}
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance""",
        (_serialize(query_vec), k),
    )
    return [_row_to_dict(cursor, row) for row in cursor]


def knn_search_with_metadata(
    conn: apsw.Connection,
    vec_table: str,
    query_vec: list[float],
    k: int = 10,
) -> list[dict]:
    """KNN search with joined metadata from embedded_assets."""
    cursor = conn.execute(
        f"""SELECT v.sha256, v.distance,
                   e.content_type, e.source_path, e.manifest_path
            FROM {vec_table} v
            JOIN embedded_assets e ON v.sha256 = e.sha256
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance""",
        (_serialize(query_vec), k),
    )
    return [_row_to_dict(cursor, row) for row in cursor]


def count_embeddings(conn: apsw.Connection, table: str) -> int:
    """Count rows in a vec table."""
    for row in conn.execute(f"SELECT COUNT(*) FROM {table}"):
        return row[0]
    return 0


def db_stats(conn: apsw.Connection) -> dict:
    """Summary counts across all tables."""
    tables = ["vec_images", "vec_text", "vec_documents",
              "vec_images_768", "vec_images_1536"]
    stats = {}
    for t in tables:
        try:
            stats[t] = count_embeddings(conn, t)
        except Exception:
            stats[t] = 0
    stats["embedded_assets"] = count_embeddings(conn, "embedded_assets")
    return stats
