"""Catalog refresh — ingest local run metadata and manifests into cache tables.

Reads from data/photos/runs/ and data/documents/runs/ to populate the
runs, photo_quality, and doc_quality tables in catalog.db. This makes the
dashboard fully independent of NAS mounts and filesystem walks.

Usage: python -m src.catalog refresh
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .catalog import set_meta

log = logging.getLogger(__name__)


def refresh_runs(conn: sqlite3.Connection) -> int:
    """Walk run directories and upsert into the runs table."""
    count = 0

    for content_type, runs_dir in [
        ("photo", config.AI_LAYER_DIR / "runs"),
        ("document", config.DOC_AI_LAYER_DIR / "runs"),
    ]:
        if not runs_dir.exists():
            continue
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            meta_path = run_dir / "run_meta.json"
            if not meta_path.exists():
                continue
            try:
                raw = meta_path.read_text()
                meta = json.loads(raw)
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Skipping run %s: %s", run_dir.name, e)
                continue

            elapsed = meta.get("elapsed_seconds", 0)
            total = meta.get("total", 0)
            pph = round(total / (elapsed / 3600), 1) if elapsed > 0 else 0

            # Doc runs use "doc_slice_path", photo runs use "slice_path"
            slice_path = meta.get("slice_path") or meta.get("doc_slice_path", "")

            conn.execute("""
                INSERT OR REPLACE INTO runs
                    (run_id, content_type, slice_path, completed,
                     elapsed_seconds, total, succeeded, failed,
                     model, photos_per_hour, raw_meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_dir.name,
                content_type,
                slice_path,
                meta.get("completed", ""),
                elapsed,
                total,
                meta.get("succeeded", 0),
                meta.get("failed", 0),
                meta.get("model") or meta.get("provider", ""),
                pph,
                raw,
            ))
            count += 1

    conn.commit()
    return count


def refresh_photo_quality(conn: sqlite3.Connection) -> int:
    """Walk photo manifest files and upsert into photo_quality table."""
    runs_dir = config.AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return 0

    count = 0
    for run_dir in sorted(runs_dir.iterdir()):
        manifests_dir = run_dir / "manifests"
        if not manifests_dir.exists():
            continue
        run_id = run_dir.name

        for mf in manifests_dir.glob("*.json"):
            try:
                data = json.loads(mf.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            sha = data.get("source_sha256", "")
            if not sha:
                continue
            analysis = data.get("analysis", {})

            dc = analysis.get("date_confidence", 0)
            if dc >= config.CONFIDENCE_HIGH:
                bucket = "high"
            elif dc >= config.CONFIDENCE_LOW:
                bucket = "medium"
            else:
                bucket = "low"

            has_loc = 1 if analysis.get("location_estimate", "").strip() else 0

            date_est = analysis.get("date_estimate", "")
            era = ""
            if date_est and len(date_est) >= 4:
                try:
                    era = date_est[:3] + "0s"
                except (ValueError, IndexError):
                    pass

            conn.execute("""
                INSERT OR REPLACE INTO photo_quality
                    (sha256, confidence_bucket, date_confidence, has_location,
                     people_count, date_estimate, era_decade, tags, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sha,
                bucket,
                dc,
                has_loc,
                analysis.get("people_count") or 0,
                date_est,
                era,
                json.dumps(analysis.get("tags", [])),
                run_id,
            ))
            count += 1

    conn.commit()
    return count


def refresh_doc_quality(conn: sqlite3.Connection) -> int:
    """Walk document manifest files and upsert into doc_quality table."""
    runs_dir = config.DOC_AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return 0

    count = 0
    for run_dir in sorted(runs_dir.iterdir()):
        manifests_dir = run_dir / "manifests"
        if not manifests_dir.exists():
            continue
        run_id = run_dir.name

        for mf in manifests_dir.glob("*.json"):
            try:
                data = json.loads(mf.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            sha = data.get("source_sha256", "")
            if not sha:
                continue
            analysis = data.get("analysis", {})
            sens = analysis.get("sensitivity", {})

            conn.execute("""
                INSERT OR REPLACE INTO doc_quality
                    (sha256, document_type, page_count,
                     has_ssn, has_financial, has_medical,
                     language, quality, doc_date, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sha,
                analysis.get("document_type", "unknown"),
                data.get("page_count", 0),
                1 if sens.get("has_ssn") else 0,
                1 if sens.get("has_financial") else 0,
                1 if sens.get("has_medical") else 0,
                analysis.get("language", "unknown") or "unknown",
                analysis.get("quality", "unknown") or "unknown",
                analysis.get("date", ""),
                run_id,
            ))
            count += 1

    conn.commit()
    return count


def refresh_all(conn: sqlite3.Connection) -> dict:
    """Run all refresh steps and update last_refresh_at timestamp."""
    log.info("Refreshing catalog cache tables...")

    runs = refresh_runs(conn)
    log.info("  Runs: %d ingested", runs)

    photos = refresh_photo_quality(conn)
    log.info("  Photo quality: %d manifests", photos)

    docs = refresh_doc_quality(conn)
    log.info("  Doc quality: %d manifests", docs)

    now = datetime.now(timezone.utc).isoformat()
    set_meta(conn, "last_refresh_at", now)
    log.info("Refresh complete — last_refresh_at: %s", now)

    return {"runs": runs, "photo_quality": photos, "doc_quality": docs}
