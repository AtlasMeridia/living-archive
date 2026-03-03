"""Archive Dashboard — read-only overview of pipeline state and archive health.

Run: python -m src.dashboard
Opens localhost:8378 with stats, quality metrics, search, and health checks.

All data served from catalog.db cache tables. No NAS access required.
Populate data first: python -m src.catalog scan && python -m src.catalog refresh
"""

import json
import logging
import re
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from . import config
from .dashboard_api import (
    api_overview,
    api_photo_runs,
    api_photo_quality,
    api_batch_progress,
    api_doc_corpus,
    api_doc_search,
    api_people,
    api_health,
)
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
            self._json(cached("overview", api_overview))
        elif path == "/api/photo-runs":
            self._json(cached("photo-runs", api_photo_runs))
        elif path == "/api/photo-quality":
            self._json(cached("photo-quality", api_photo_quality))
        elif path == "/api/batch-progress":
            self._json(cached("batch-progress", api_batch_progress))
        elif path == "/api/doc-corpus":
            self._json(cached("doc-corpus", api_doc_corpus))
        elif path == "/api/doc-search":
            qs = parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            if not q:
                self._json({"error": "Missing q parameter"}, 400)
            else:
                self._json(api_doc_search(q))
        elif path == "/api/people":
            self._json(cached("people", api_people))
        elif path == "/api/health":
            self._json(api_health())
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
    log.info("  Data: %s", config.DATA_DIR)
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
