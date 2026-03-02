"""Archive Dashboard — read-only overview of pipeline state and archive health.

Run: python -m src.dashboard
Opens localhost:8378 with stats, quality metrics, search, and health checks.
"""

import json
import logging
import re
import time
import webbrowser
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from . import config
from .tokens import generate_css

log = logging.getLogger("living_archive")

PORT = 8378
HTML_PATH = Path(__file__).resolve().parent.parent / "dashboard.html"

# --- In-memory TTL cache ---

_cache: dict[str, tuple[object, float]] = {}
CACHE_TTL = 60


def cached(key: str, fn):
    now = time.time()
    if key in _cache and now - _cache[key][1] < CACHE_TTL:
        return _cache[key][0]
    result = fn()
    _cache[key] = (result, now)
    return result


# --- Data helpers ---


def _api_overview() -> dict:
    from .catalog import get_catalog_db, init_catalog, get_stats

    db_path = get_catalog_db("family")
    stats = {}
    if db_path.exists():
        conn = init_catalog(db_path)
        stats = get_stats(conn)
        conn.close()

    # Count runs by walking run directories
    photo_runs = 0
    doc_runs = 0
    photo_runs_dir = config.AI_LAYER_DIR / "runs"
    doc_runs_dir = config.DOC_AI_LAYER_DIR / "runs"
    if photo_runs_dir.exists():
        photo_runs = sum(1 for d in photo_runs_dir.iterdir() if d.is_dir())
    if doc_runs_dir.exists():
        doc_runs = sum(1 for d in doc_runs_dir.iterdir() if d.is_dir())

    # People count
    try:
        from .people import load_registry
        registry = load_registry()
        people_count = len(registry.people)
    except Exception:
        people_count = 0

    return {
        "catalog_stats": stats,
        "photo_runs": photo_runs,
        "doc_runs": doc_runs,
        "people_count": people_count,
    }


def _api_photo_runs() -> list[dict]:
    runs_dir = config.AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return []
    runs = []
    for d in sorted(runs_dir.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta_path = d / "run_meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        elapsed = meta.get("elapsed_seconds", 0)
        total = meta.get("total", 0)
        pph = round(total / (elapsed / 3600), 1) if elapsed > 0 else 0
        runs.append({
            "run_id": d.name,
            "date": meta.get("completed", d.name),
            "slice_path": meta.get("slice_path", ""),
            "total": total,
            "succeeded": meta.get("succeeded", 0),
            "failed": meta.get("failed", 0),
            "elapsed_seconds": elapsed,
            "model": meta.get("model", meta.get("method", "")),
            "photos_per_hour": pph,
        })
    return runs


def _api_photo_quality() -> dict:
    runs_dir = config.AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return {"confidence": {}, "location_coverage": 0, "people_histogram": {},
                "top_tags": [], "era_breakdown": {}}

    high = medium = low = 0
    has_location = 0
    total = 0
    people_bins = {"0": 0, "1": 0, "2-5": 0, "6+": 0}
    tag_counts: dict[str, int] = {}
    era_counts: dict[str, int] = {}

    for run_dir in runs_dir.iterdir():
        manifests_dir = run_dir / "manifests"
        if not manifests_dir.exists():
            continue
        for mf in manifests_dir.glob("*.json"):
            try:
                data = json.loads(mf.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            analysis = data.get("analysis", {})
            total += 1

            # Date confidence
            dc = analysis.get("date_confidence", 0)
            if dc >= config.CONFIDENCE_HIGH:
                high += 1
            elif dc >= config.CONFIDENCE_LOW:
                medium += 1
            else:
                low += 1

            # Location
            if analysis.get("location_estimate", "").strip():
                has_location += 1

            # People count
            pc = analysis.get("people_count") or 0
            if pc == 0:
                people_bins["0"] += 1
            elif pc == 1:
                people_bins["1"] += 1
            elif pc <= 5:
                people_bins["2-5"] += 1
            else:
                people_bins["6+"] += 1

            # Tags
            for tag in analysis.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

            # Era by decade
            date_est = analysis.get("date_estimate", "")
            if date_est and len(date_est) >= 4:
                try:
                    decade = date_est[:3] + "0s"
                    era_counts[decade] = era_counts.get(decade, 0) + 1
                except (ValueError, IndexError):
                    pass

    top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:20]

    return {
        "total": total,
        "confidence": {"high": high, "medium": medium, "low": low},
        "location_coverage": has_location,
        "people_histogram": people_bins,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "era_breakdown": dict(sorted(era_counts.items())),
    }


def _api_batch_progress() -> dict:
    try:
        from .discover import build_batch_work_list
        work_list = build_batch_work_list(config.MEDIA_ROOT)
    except Exception as e:
        log.warning("batch_progress failed: %s", e)
        return {"slices": [], "totals": {"slices_remaining": 0,
                "photos_remaining": 0, "photos_done": 0}}

    slices = []
    total_remaining = 0
    total_done = 0
    for w in work_list:
        pct = round(w["done"] / w["total"] * 100, 1) if w["total"] > 0 else 0
        slices.append({
            "slice_path": w["slice_path"],
            "total": w["total"],
            "done": w["done"],
            "remaining": w["remaining"],
            "pct_done": pct,
        })
        total_remaining += w["remaining"]
        total_done += w["done"]

    return {
        "slices": slices,
        "totals": {
            "slices_remaining": len(work_list),
            "photos_remaining": total_remaining,
            "photos_done": total_done,
        },
    }


def _api_doc_corpus() -> dict:
    runs_dir = config.DOC_AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return {"total": 0, "types": {}, "sensitivity": {},
                "languages": {}, "quality": {}, "total_pages": 0}

    type_counts: dict[str, int] = {}
    sens_counts = {"ssn": 0, "financial": 0, "medical": 0}
    lang_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}
    total = 0
    total_pages = 0
    dates: list[str] = []

    for run_dir in runs_dir.iterdir():
        manifests_dir = run_dir / "manifests"
        if not manifests_dir.exists():
            continue
        for mf in manifests_dir.glob("*.json"):
            try:
                data = json.loads(mf.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            analysis = data.get("analysis", {})
            total += 1
            total_pages += data.get("page_count", 0)

            dt = analysis.get("document_type", "unknown")
            type_counts[dt] = type_counts.get(dt, 0) + 1

            sens = analysis.get("sensitivity", {})
            if sens.get("has_ssn"):
                sens_counts["ssn"] += 1
            if sens.get("has_financial"):
                sens_counts["financial"] += 1
            if sens.get("has_medical"):
                sens_counts["medical"] += 1

            lang = analysis.get("language", "unknown") or "unknown"
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

            q = analysis.get("quality", "unknown") or "unknown"
            quality_counts[q] = quality_counts.get(q, 0) + 1

            d = analysis.get("date", "")
            if d:
                dates.append(d)

    dates.sort()
    return {
        "total": total,
        "types": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "sensitivity": sens_counts,
        "languages": lang_counts,
        "quality": quality_counts,
        "total_pages": total_pages,
        "date_range": {"earliest": dates[0], "latest": dates[-1]} if dates else None,
    }


def _api_doc_search(query: str) -> list[dict]:
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


def _api_people() -> dict:
    from .people import load_registry
    from . import immich

    registry = load_registry()
    people_list = []

    # Try to get Immich data
    immich_stats: dict[str, int] = {}
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


def _api_health() -> dict:
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
    from .catalog import get_catalog_db, SCHEMA_VERSION
    db_path = get_catalog_db("family")
    cat_ok = db_path.exists()
    checks.append({
        "name": "Catalog",
        "ok": cat_ok,
        "detail": f"{db_path.name} (schema v{SCHEMA_VERSION})" if cat_ok else "Not found",
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


# --- HTTP handler ---


class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        log.debug("HTTP %s", format % args)

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_html()
        elif path == "/tokens.css":
            self._serve_tokens_css()
        elif path == "/api/overview":
            self._json(cached("overview", _api_overview))
        elif path == "/api/photo-runs":
            self._json(cached("photo-runs", _api_photo_runs))
        elif path == "/api/photo-quality":
            self._json(cached("photo-quality", _api_photo_quality))
        elif path == "/api/batch-progress":
            self._json(cached("batch-progress", _api_batch_progress))
        elif path == "/api/doc-corpus":
            self._json(cached("doc-corpus", _api_doc_corpus))
        elif path == "/api/doc-search":
            qs = parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            if not q:
                self._json({"error": "Missing q parameter"}, 400)
            else:
                self._json(_api_doc_search(q))
        elif path == "/api/people":
            self._json(cached("people", _api_people))
        elif path == "/api/health":
            self._json(_api_health())
        elif m := re.match(r"^/api/immich/thumbnail/([^/]+)$", path):
            self._proxy_thumbnail(m.group(1))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/cache/flush":
            _cache.clear()
            self._json({"ok": True, "message": "Cache cleared"})
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_html(self):
        if not HTML_PATH.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "dashboard.html not found")
            return
        body = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_tokens_css(self):
        try:
            css = generate_css()
            body = css.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError as e:
            self.send_error(HTTPStatus.NOT_FOUND, str(e))

    def _proxy_thumbnail(self, person_id: str):
        try:
            url = config.IMMICH_URL.rstrip("/") + f"/api/people/{person_id}/thumbnail"
            resp = httpx.get(
                url,
                headers={"x-api-key": config.IMMICH_API_KEY},
                timeout=10.0,
            )
            resp.raise_for_status()
            self.send_response(200)
            self.send_header("Content-Type", resp.headers.get("content-type", "image/jpeg"))
            self.send_header("Content-Length", str(len(resp.content)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            log.warning("Thumbnail proxy failed for %s: %s", person_id, e)
            self.send_error(HTTPStatus.BAD_GATEWAY, str(e))


# --- Entry point ---


def main():
    config.setup_logging()
    log.info("Living Archive — Archive Dashboard")
    log.info("  Media:  %s", config.MEDIA_ROOT)
    log.info("  Docs:   %s", config.DOCUMENTS_ROOT)
    log.info("  Starting server on http://0.0.0.0:%d", PORT)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    webbrowser.open(f"http://localhost:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
