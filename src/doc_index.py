"""SQLite FTS5 full-text search index for extracted documents."""

import json
import logging
import sqlite3
from pathlib import Path

from . import config
from .doc_manifest import list_manifests, load_manifest, text_dir

log = logging.getLogger(__name__)


def db_path(run_id: str) -> Path:
    """Return the path to the index database for a run."""
    return config.DOC_AI_LAYER_DIR / "runs" / run_id / "index.db"


def build_index(run_id: str) -> Path:
    """Build or rebuild the FTS5 index from manifests and extracted text.

    Returns path to the created database.
    """
    index_path = db_path(run_id)
    td = text_dir(run_id)

    # Remove existing index to rebuild
    if index_path.exists():
        index_path.unlink()

    conn = sqlite3.connect(str(index_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # Main document table
    conn.execute("""
        CREATE TABLE documents (
            sha256 TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            file_size_bytes INTEGER,
            page_count INTEGER,
            document_type TEXT,
            title TEXT,
            date TEXT,
            date_confidence REAL,
            summary_en TEXT,
            summary_zh TEXT,
            has_ssn INTEGER DEFAULT 0,
            has_financial INTEGER DEFAULT 0,
            has_medical INTEGER DEFAULT 0,
            tags TEXT,
            quality TEXT,
            manifest_json TEXT
        )
    """)

    # FTS5 virtual table for full-text search
    conn.execute("""
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            sha256 UNINDEXED,
            source_file,
            title,
            summary_en,
            summary_zh,
            extracted_text,
            tags,
            key_people,
            content=documents_fts_content
        )
    """)

    # Content table backing FTS5
    conn.execute("""
        CREATE TABLE documents_fts_content (
            sha256 TEXT PRIMARY KEY,
            source_file TEXT,
            title TEXT,
            summary_en TEXT,
            summary_zh TEXT,
            extracted_text TEXT,
            tags TEXT,
            key_people TEXT
        )
    """)

    manifests = list_manifests(run_id)
    indexed = 0

    for mp in manifests:
        data = load_manifest(mp)
        sha = data["source_sha256"]
        analysis = data.get("analysis", {})
        sensitivity = analysis.get("sensitivity", {})

        # Load extracted text
        text_path = td / f"{sha[:12]}.txt"
        extracted_text = text_path.read_text() if text_path.exists() else ""

        tags_str = ", ".join(analysis.get("tags", []))
        people_str = ", ".join(analysis.get("key_people", []))

        # Insert into main table
        conn.execute("""
            INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sha,
            data["source_file"],
            data.get("file_size_bytes"),
            data.get("page_count"),
            analysis.get("document_type"),
            analysis.get("title"),
            analysis.get("date"),
            analysis.get("date_confidence"),
            analysis.get("summary_en"),
            analysis.get("summary_zh"),
            1 if sensitivity.get("has_ssn") else 0,
            1 if sensitivity.get("has_financial") else 0,
            1 if sensitivity.get("has_medical") else 0,
            tags_str,
            analysis.get("quality"),
            json.dumps(data, ensure_ascii=False),
        ))

        # Insert into FTS content + index
        conn.execute("""
            INSERT INTO documents_fts_content VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sha, data["source_file"], analysis.get("title", ""),
              analysis.get("summary_en", ""), analysis.get("summary_zh", ""),
              extracted_text, tags_str, people_str))

        conn.execute("""
            INSERT INTO documents_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sha, data["source_file"], analysis.get("title", ""),
              analysis.get("summary_en", ""), analysis.get("summary_zh", ""),
              extracted_text, tags_str, people_str))

        indexed += 1

    conn.commit()
    conn.close()

    log.info("Index built: %d documents -> %s", indexed, index_path)
    return index_path


def search(query: str, index_path: Path, limit: int = 20) -> list[dict]:
    """Search the FTS5 index. Returns list of matching documents."""
    conn = sqlite3.connect(str(index_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            d.source_file,
            d.title,
            d.document_type,
            d.date,
            d.summary_en,
            d.has_ssn,
            d.has_financial,
            d.has_medical,
            d.tags,
            highlight(documents_fts, 5, '>>>', '<<<') as text_snippet
        FROM documents_fts
        JOIN documents d ON d.sha256 = documents_fts.sha256
        WHERE documents_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()

    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        # Truncate text snippet
        snippet = r.get("text_snippet", "")
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        r["text_snippet"] = snippet
        results.append(r)

    return results


def main():
    """CLI: build index or search."""
    import sys
    _log = config.setup_logging()

    if len(sys.argv) < 2:
        _log.info("Usage:")
        _log.info("  python -m src.doc_index build RUN_ID")
        _log.info("  python -m src.doc_index search RUN_ID 'query text'")
        sys.exit(1)

    command = sys.argv[1]

    if command == "build":
        if len(sys.argv) < 3:
            _log.info("Usage: python -m src.doc_index build RUN_ID")
            sys.exit(1)
        run_id = sys.argv[2]
        build_index(run_id)

    elif command == "search":
        if len(sys.argv) < 4:
            _log.info("Usage: python -m src.doc_index search RUN_ID 'query'")
            sys.exit(1)
        run_id = sys.argv[2]
        query = sys.argv[3]
        ip = db_path(run_id)

        if not ip.exists():
            _log.error("Index not found: %s", ip)
            _log.info("Run: python -m src.doc_index build %s", run_id)
            sys.exit(1)

        results = search(query, ip)
        if not results:
            _log.info("No results found.")
            return

        _log.info("Found %d results for '%s':", len(results), query)
        _log.info("")
        for i, r in enumerate(results, 1):
            sensitivity = []
            if r["has_ssn"]:
                sensitivity.append("SSN")
            if r["has_financial"]:
                sensitivity.append("FINANCIAL")
            if r["has_medical"]:
                sensitivity.append("MEDICAL")
            sens_str = f" [{', '.join(sensitivity)}]" if sensitivity else ""

            _log.info("  [%d] %s", i, r["title"] or r["source_file"])
            _log.info("      Type: %s  Date: %s%s", r["document_type"], r["date"], sens_str)
            if r["summary_en"]:
                _log.info("      %s", r["summary_en"][:120])
            if r["text_snippet"]:
                _log.info("      ...%s...", r["text_snippet"][:150])
            _log.info("")
    else:
        _log.error("Unknown command: %s", command)
        sys.exit(1)


if __name__ == "__main__":
    main()
