"""Dashboard API functions for catalog + synthesis derived data.

No NAS access, no filesystem walks. Catalog metrics come from `catalog.db`;
synthesis/cross-reference metrics come from `synthesis.db` and
`chronology.json`.
"""

import json
import logging
import sqlite3
import time

from . import config
from .catalog import get_catalog_db, init_catalog, get_stats, get_meta
from .synthesis_queries import (
    chronology_metadata,
    chronology_payload,
    open_synthesis_db,
    query_date_entities,
    query_location_entity,
    query_overview,
    query_person_entity,
)

log = logging.getLogger("living_archive")


def _get_conn() -> sqlite3.Connection:
    """Get a catalog connection (cached per-call, caller should not close)."""
    db_path = get_catalog_db("family")
    if not db_path.exists():
        raise FileNotFoundError(f"Catalog not found: {db_path}")
    return init_catalog(db_path)


def _catalog_asset_map(sha_values: list[str]) -> dict[str, dict]:
    """Resolve sha256 -> catalog context (path, content type, cached dates/types)."""
    if not sha_values:
        return {}
    try:
        conn = _get_conn()
    except FileNotFoundError:
        return {}

    placeholders = ",".join("?" * len(sha_values))
    rows = conn.execute(f"""
        SELECT a.sha256,
               a.path,
               a.content_type,
               pq.date_estimate,
               dq.doc_date,
               dq.document_type
        FROM assets a
        LEFT JOIN photo_quality pq ON pq.sha256 = a.sha256
        LEFT JOIN doc_quality dq ON dq.sha256 = a.sha256
        WHERE a.sha256 IN ({placeholders})
    """, sha_values).fetchall()
    conn.close()

    out: dict[str, dict] = {}
    for r in rows:
        out[r["sha256"]] = {
            "source_file": r["path"],
            "content_type": r["content_type"],
            "photo_date": r["date_estimate"],
            "doc_date": r["doc_date"],
            "document_type": r["document_type"],
        }
    return out


def api_overview() -> dict:
    """Catalog stats, run counts, and people count."""
    try:
        conn = _get_conn()
    except FileNotFoundError:
        return {"catalog_stats": {}, "photo_runs": 0, "doc_runs": 0,
                "people_count": 0}

    stats = get_stats(conn)

    photo_runs = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE content_type='photo'"
    ).fetchone()[0]
    doc_runs = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE content_type='document'"
    ).fetchone()[0]

    try:
        from .people import load_registry
        people_count = len(load_registry().people)
    except Exception:
        people_count = 0

    conn.close()
    return {
        "catalog_stats": stats,
        "photo_runs": photo_runs,
        "doc_runs": doc_runs,
        "people_count": people_count,
    }


def api_photo_runs() -> list[dict]:
    """All photo runs from the runs cache table."""
    try:
        conn = _get_conn()
    except FileNotFoundError:
        return []

    rows = conn.execute("""
        SELECT run_id, completed, slice_path, total, succeeded, failed,
               elapsed_seconds, model, photos_per_hour
        FROM runs WHERE content_type='photo'
        ORDER BY run_id DESC
    """).fetchall()

    runs = []
    for r in rows:
        runs.append({
            "run_id": r["run_id"],
            "date": r["completed"] or r["run_id"],
            "slice_path": r["slice_path"] or "",
            "total": r["total"] or 0,
            "succeeded": r["succeeded"] or 0,
            "failed": r["failed"] or 0,
            "elapsed_seconds": r["elapsed_seconds"] or 0,
            "model": r["model"] or "",
            "photos_per_hour": r["photos_per_hour"] or 0,
        })

    conn.close()
    return runs


def api_photo_quality() -> dict:
    """Photo quality metrics from photo_quality cache table."""
    try:
        conn = _get_conn()
    except FileNotFoundError:
        return {"confidence": {}, "location_coverage": 0,
                "people_histogram": {}, "top_tags": [], "era_breakdown": {}}

    total = conn.execute("SELECT COUNT(*) FROM photo_quality").fetchone()[0]
    if total == 0:
        conn.close()
        return {"total": 0, "confidence": {"high": 0, "medium": 0, "low": 0},
                "location_coverage": 0, "people_histogram": {},
                "top_tags": [], "era_breakdown": {}}

    # Confidence buckets
    conf_rows = conn.execute("""
        SELECT confidence_bucket, COUNT(*) as cnt
        FROM photo_quality GROUP BY confidence_bucket
    """).fetchall()
    confidence = {"high": 0, "medium": 0, "low": 0}
    for r in conf_rows:
        if r["confidence_bucket"] in confidence:
            confidence[r["confidence_bucket"]] = r["cnt"]

    # Location coverage
    has_location = conn.execute(
        "SELECT COUNT(*) FROM photo_quality WHERE has_location=1"
    ).fetchone()[0]

    # People histogram
    people_bins = {"0": 0, "1": 0, "2-5": 0, "6+": 0}
    people_rows = conn.execute("""
        SELECT
            CASE
                WHEN people_count = 0 THEN '0'
                WHEN people_count = 1 THEN '1'
                WHEN people_count <= 5 THEN '2-5'
                ELSE '6+'
            END as bin,
            COUNT(*) as cnt
        FROM photo_quality GROUP BY bin
    """).fetchall()
    for r in people_rows:
        people_bins[r["bin"]] = r["cnt"]

    # Top tags — aggregate across all JSON tag arrays
    tag_counts: dict[str, int] = {}
    tag_rows = conn.execute(
        "SELECT tags FROM photo_quality WHERE tags IS NOT NULL AND tags != '[]'"
    ).fetchall()
    for r in tag_rows:
        try:
            for tag in json.loads(r["tags"]):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:20]

    # Era breakdown
    era_rows = conn.execute("""
        SELECT era_decade, COUNT(*) as cnt
        FROM photo_quality
        WHERE era_decade IS NOT NULL AND era_decade != ''
        GROUP BY era_decade ORDER BY era_decade
    """).fetchall()
    era_breakdown = {r["era_decade"]: r["cnt"] for r in era_rows}

    conn.close()
    return {
        "total": total,
        "confidence": confidence,
        "location_coverage": has_location,
        "people_histogram": people_bins,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "era_breakdown": era_breakdown,
    }


def api_batch_progress() -> dict:
    """Batch progress from assets table — grouped by slice."""
    try:
        conn = _get_conn()
    except FileNotFoundError:
        return {"slices": [], "totals": {"slices_remaining": 0,
                "photos_remaining": 0, "photos_done": 0}}

    rows = conn.execute("""
        SELECT slice,
               SUM(CASE WHEN status='indexed' THEN 1 ELSE 0 END) as done,
               SUM(CASE WHEN status='discovered' THEN 1 ELSE 0 END) as remaining,
               COUNT(*) as total
        FROM assets
        WHERE content_type='photo'
        GROUP BY slice
        HAVING remaining > 0
        ORDER BY remaining ASC
    """).fetchall()

    slices = []
    total_remaining = 0
    total_done = 0
    for r in rows:
        total_count = r["total"]
        done_count = r["done"]
        rem_count = r["remaining"]
        pct = round(done_count / total_count * 100, 1) if total_count > 0 else 0
        slices.append({
            "slice_path": r["slice"] or "",
            "total": total_count,
            "done": done_count,
            "remaining": rem_count,
            "pct_done": pct,
        })
        total_remaining += rem_count
        total_done += done_count

    conn.close()
    return {
        "slices": slices,
        "totals": {
            "slices_remaining": len(slices),
            "photos_remaining": total_remaining,
            "photos_done": total_done,
        },
    }


def api_doc_corpus() -> dict:
    """Document corpus metrics from doc_quality cache table."""
    try:
        conn = _get_conn()
    except FileNotFoundError:
        return {"total": 0, "types": {}, "sensitivity": {},
                "languages": {}, "quality": {}, "total_pages": 0}

    total = conn.execute("SELECT COUNT(*) FROM doc_quality").fetchone()[0]
    if total == 0:
        conn.close()
        return {"total": 0, "types": {}, "sensitivity": {},
                "languages": {}, "quality": {}, "total_pages": 0}

    # Document types
    type_rows = conn.execute("""
        SELECT document_type, COUNT(*) as cnt
        FROM doc_quality GROUP BY document_type ORDER BY cnt DESC
    """).fetchall()
    types = {r["document_type"]: r["cnt"] for r in type_rows}

    # Sensitivity
    ssn = conn.execute("SELECT COUNT(*) FROM doc_quality WHERE has_ssn=1").fetchone()[0]
    fin = conn.execute("SELECT COUNT(*) FROM doc_quality WHERE has_financial=1").fetchone()[0]
    med = conn.execute("SELECT COUNT(*) FROM doc_quality WHERE has_medical=1").fetchone()[0]

    # Languages
    lang_rows = conn.execute("""
        SELECT language, COUNT(*) as cnt FROM doc_quality GROUP BY language
    """).fetchall()
    languages = {r["language"]: r["cnt"] for r in lang_rows}

    # Quality
    qual_rows = conn.execute("""
        SELECT quality, COUNT(*) as cnt FROM doc_quality GROUP BY quality
    """).fetchall()
    quality = {r["quality"]: r["cnt"] for r in qual_rows}

    # Total pages
    total_pages = conn.execute(
        "SELECT COALESCE(SUM(page_count), 0) FROM doc_quality"
    ).fetchone()[0]

    # Date range
    dates = conn.execute("""
        SELECT doc_date FROM doc_quality
        WHERE doc_date IS NOT NULL AND doc_date != ''
        ORDER BY doc_date
    """).fetchall()
    date_list = [r["doc_date"] for r in dates]

    conn.close()
    return {
        "total": total,
        "types": types,
        "sensitivity": {"ssn": ssn, "financial": fin, "medical": med},
        "languages": languages,
        "quality": quality,
        "total_pages": total_pages,
        "date_range": {"earliest": date_list[0], "latest": date_list[-1]} if date_list else None,
    }


def api_doc_search(query: str) -> list[dict]:
    """Full-text search across document indexes (unchanged — uses index.db)."""
    from . import doc_index

    runs_dir = config.DOC_AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return []

    seen_files: set[str] = set()
    results: list[dict] = []

    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        index_path = run_dir / "index.db"
        if not index_path.exists():
            continue
        try:
            hits = doc_index.search(query, index_path, limit=20)
        except Exception:
            continue
        for hit in hits:
            sf = hit.get("source_file", "")
            if sf in seen_files:
                continue
            seen_files.add(sf)
            results.append(hit)
            if len(results) >= 20:
                return results
    return results


def api_people() -> dict:
    """People registry with Immich photo counts (unchanged — live data)."""
    from .people import load_registry
    from . import immich

    registry = load_registry()
    people_list = []
    total_clusters = 0

    try:
        client = immich._client()
        all_people = immich.list_people(client)
        total_clusters = len(all_people)

        for person in registry.people:
            asset_count = 0
            primary_immich_id = None
            for pid in person.immich_person_ids:
                primary_immich_id = primary_immich_id or pid
                try:
                    stats = immich.get_person_statistics(client, pid)
                    asset_count += stats.get("assets", 0)
                except Exception:
                    pass
            people_list.append({
                "person_id": person.person_id,
                "name_en": person.name_en,
                "name_zh": person.name_zh,
                "relationship": person.relationship,
                "birth_year": person.birth_year,
                "immich_person_id": primary_immich_id,
                "photo_count": asset_count,
            })
        client.close()
    except Exception as e:
        log.warning("People API — Immich unavailable: %s", e)
        for person in registry.people:
            people_list.append({
                "person_id": person.person_id,
                "name_en": person.name_en,
                "name_zh": person.name_zh,
                "relationship": person.relationship,
                "birth_year": person.birth_year,
                "immich_person_id": person.immich_person_ids[0] if person.immich_person_ids else None,
                "photo_count": 0,
            })

    named = sum(1 for p in people_list if p["name_en"])
    return {
        "total_clusters": total_clusters,
        "named": named,
        "unnamed": total_clusters - named,
        "people": people_list,
    }


def api_synthesis_overview() -> dict:
    """Top-level synthesis metrics for dashboard use."""
    try:
        conn = open_synthesis_db()
    except FileNotFoundError as e:
        return {"available": False, "error": str(e)}
    try:
        overview = query_overview(conn)
    finally:
        conn.close()

    return {
        "available": True,
        **overview,
        "chronology": chronology_metadata(),
    }


def api_synthesis_person(name: str) -> dict:
    """Person dossier query via synthesis.db + catalog context."""
    try:
        conn = open_synthesis_db()
    except FileNotFoundError as e:
        return {"error": str(e)}
    try:
        person = query_person_entity(conn, name)
    finally:
        conn.close()
    if not person:
        return {"error": f"No person entity matching '{name}'"}

    links = person["links"]
    shas = [r["asset_sha256"] for r in links]
    catalog_map = _catalog_asset_map(shas)

    documents: list[dict] = []
    photos: list[dict] = []
    for r in links:
        sha = r["asset_sha256"]
        ctx = catalog_map.get(sha, {})
        item = {
            "sha256": sha[:12],
            "source": r["source"],
            "confidence": r["confidence"],
            "context": r["context"],
            "source_file": ctx.get("source_file"),
        }
        content_type = ctx.get("content_type")
        if content_type == "photo":
            item["date"] = ctx.get("photo_date")
            photos.append(item)
        else:
            item["date"] = ctx.get("doc_date")
            item["document_type"] = ctx.get("document_type")
            documents.append(item)

    documents.sort(key=lambda x: x.get("date") or "")
    photos.sort(key=lambda x: x.get("date") or "")
    return {
        "person": person["entity_value"],
        "name_zh": person["name_zh"],
        "family_role": person["family_role"],
        "total_links": len(links),
        "documents": documents,
        "photos": photos,
    }


def api_synthesis_date(year: str) -> dict:
    """Date query in synthesis layer."""
    try:
        conn = open_synthesis_db()
    except FileNotFoundError as e:
        return {"error": str(e)}
    try:
        date_result = query_date_entities(conn, year)
    finally:
        conn.close()
    if not date_result:
        return {"error": f"No date entities matching '{year}'"}

    links = date_result["links"]
    shas = [r["asset_sha256"] for r in links]
    catalog_map = _catalog_asset_map(shas)
    documents: list[dict] = []
    photos: list[dict] = []
    for r in links:
        sha = r["asset_sha256"]
        ctx = catalog_map.get(sha, {})
        item = {
            "sha256": sha[:12],
            "date": r["normalized_value"],
            "source": r["source"],
            "confidence": r["confidence"],
            "source_file": ctx.get("source_file"),
        }
        if ctx.get("content_type") == "photo":
            photos.append(item)
        else:
            item["document_type"] = ctx.get("document_type")
            documents.append(item)

    return {
        "query": year,
        "dates_matched": date_result["dates_matched"],
        "total_assets": len(links),
        "documents": documents,
        "photos": photos,
    }


def api_synthesis_location(country: str) -> dict:
    """Location query in synthesis layer."""
    try:
        conn = open_synthesis_db()
    except FileNotFoundError as e:
        return {"error": str(e)}
    try:
        location_result = query_location_entity(conn, country)
    finally:
        conn.close()
    if not location_result:
        return {"error": f"No location entity matching '{country}'"}
    links = location_result["links"]
    shas = [r["asset_sha256"] for r in links]
    catalog_map = _catalog_asset_map(shas)
    photos = []
    for r in links:
        sha = r["asset_sha256"]
        ctx = catalog_map.get(sha, {})
        photos.append({
            "sha256": sha[:12],
            "confidence": r["confidence"],
            "location_detail": r["context"],
            "source_file": ctx.get("source_file"),
            "date": ctx.get("photo_date"),
        })
    photos.sort(key=lambda x: x.get("date") or "")
    return {
        "location": location_result["location"],
        "total_photos": len(photos),
        "photos": photos,
    }


def api_synthesis_chronology() -> dict:
    """Return generated chronology if present."""
    return chronology_payload()


def api_health() -> dict:
    """System health checks with data freshness info."""
    checks = []

    # NAS mount
    nas_ok = config.MEDIA_ROOT.exists()
    checks.append({
        "name": "NAS Mount",
        "ok": nas_ok,
        "detail": str(config.MEDIA_ROOT) if nas_ok else f"Not found: {config.MEDIA_ROOT}",
    })

    # Immich ping
    try:
        import httpx
        t0 = time.time()
        resp = httpx.get(
            config.IMMICH_URL.rstrip("/") + "/api/server/ping",
            headers={"x-api-key": config.IMMICH_API_KEY},
            timeout=5.0,
        )
        latency_ms = round((time.time() - t0) * 1000)
        ok = resp.status_code == 200
        checks.append({
            "name": "Immich",
            "ok": ok,
            "detail": f"{config.IMMICH_URL} ({latency_ms}ms)" if ok else f"HTTP {resp.status_code}",
        })
    except Exception as e:
        checks.append({"name": "Immich", "ok": False, "detail": str(e)})

    # Claude CLI
    cli_exists = config.CLAUDE_CLI.exists()
    checks.append({
        "name": "Claude CLI",
        "ok": cli_exists,
        "detail": str(config.CLAUDE_CLI) if cli_exists else "Not found",
    })

    # Catalog
    from .catalog import SCHEMA_VERSION
    db_path = get_catalog_db("family")
    cat_ok = db_path.exists()
    checks.append({
        "name": "Catalog",
        "ok": cat_ok,
        "detail": f"{db_path.name} (schema v{SCHEMA_VERSION})" if cat_ok else "Not found",
    })

    # Data freshness
    freshness = {}
    if cat_ok:
        try:
            conn = init_catalog(db_path)
            for key in ("last_scan_at", "last_refresh_at"):
                val = get_meta(conn, key)
                freshness[key] = val or "never"
            conn.close()
        except Exception:
            pass
    checks.append({
        "name": "Data Freshness",
        "ok": bool(freshness.get("last_refresh_at", "never") != "never"),
        "detail": f"scan: {freshness.get('last_scan_at', 'never')}, "
                  f"refresh: {freshness.get('last_refresh_at', 'never')}",
    })

    # Config summary
    cfg = {
        "MEDIA_ROOT": str(config.MEDIA_ROOT),
        "DOCUMENTS_ROOT": str(config.DOCUMENTS_ROOT),
        "AI_LAYER_DIR": str(config.AI_LAYER_DIR),
        "DOC_AI_LAYER_DIR": str(config.DOC_AI_LAYER_DIR),
        "IMMICH_URL": config.IMMICH_URL,
        "MODEL": config.MODEL,
        "DOC_PROVIDER": config.DOC_PROVIDER,
    }

    return {"checks": checks, "config": cfg}
