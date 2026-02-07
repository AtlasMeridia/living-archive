"""Review dashboard server — human-in-the-loop for AI photo analysis.

Run: python -m src.review
Opens localhost:8377 with a review UI for approving/correcting AI manifests.
"""

import json
import logging
import re
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import httpx

from . import config
from .immich import (
    _client as immich_client,
    build_path_lookup,
    date_estimate_to_iso,
    search_assets_by_path,
    update_asset,
)
from .manifest import list_manifests, load_manifest
from .review_models import ReviewDecision

log = logging.getLogger("living_archive")

PORT = 8377
HTML_PATH = Path(__file__).resolve().parent.parent / "review.html"


# --- Review file I/O ---


def reviews_dir(run_id: str) -> Path:
    return config.AI_LAYER_DIR / "runs" / run_id / "reviews"


def load_review(run_id: str, sha: str) -> ReviewDecision | None:
    path = reviews_dir(run_id) / f"{sha}.review.json"
    if not path.exists():
        return None
    return ReviewDecision.model_validate(json.loads(path.read_text()))


def save_review(run_id: str, sha: str, decision: ReviewDecision) -> Path:
    d = reviews_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{sha}.review.json"
    path.write_text(json.dumps(decision.model_dump(), indent=2, ensure_ascii=False))
    return path


# --- API helpers ---


def list_runs() -> list[dict]:
    runs_root = config.AI_LAYER_DIR / "runs"
    if not runs_root.exists():
        return []
    runs = []
    for d in sorted(runs_root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta_path = d / "run_meta.json"
        meta = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        manifest_count = len(list((d / "manifests").glob("*.json"))) if (d / "manifests").exists() else 0
        review_count = len(list((d / "reviews").glob("*.review.json"))) if (d / "reviews").exists() else 0
        runs.append({
            "run_id": d.name,
            "meta": meta,
            "manifest_count": manifest_count,
            "review_count": review_count,
        })
    return runs


def _resolve_asset_ids(source_files: list[str]) -> dict[str, str]:
    """Match source filenames to Immich asset IDs. Returns {filename: asset_id}."""
    if not source_files:
        return {}
    try:
        client = immich_client()
        # Use run_meta's slice_path or derive from first file's directory
        first_dir = Path(source_files[0]).parts[0] if source_files else ""
        assets = search_assets_by_path(client, first_dir)
        path_lookup = build_path_lookup(assets)
        result = {}
        for sf in source_files:
            name = Path(sf).name
            for immich_path, aid in path_lookup.items():
                if immich_path.endswith(name):
                    result[name] = aid
                    break
        return result
    except Exception as e:
        log.warning("Could not resolve Immich asset IDs: %s", e)
        return {}


def get_run_items(run_id: str) -> list[dict]:
    manifests = list_manifests(run_id)
    items = []
    for mpath in manifests:
        m = load_manifest(mpath)
        sha = m.source_sha256[:12]
        review = load_review(run_id, sha)
        items.append({
            "sha": sha,
            "source_file": m.source_file,
            "source_sha256": m.source_sha256,
            "analysis": m.analysis.model_dump(),
            "inference": m.inference.model_dump(),
            "review": review.model_dump() if review else None,
        })

    # Resolve Immich asset IDs for thumbnails
    source_files = [it["source_file"] for it in items]
    asset_lookup = _resolve_asset_ids(source_files)
    for item in items:
        name = Path(item["source_file"]).name
        item["asset_id"] = asset_lookup.get(name)

    return items


def push_reviewed_to_immich(run_id: str) -> dict:
    """Push all reviewed (approved/corrected) items to Immich."""
    items = get_run_items(run_id)
    client = immich_client()

    pushed = 0
    skipped = 0
    errors = []

    for item in items:
        review = item.get("review")
        if not review or review["status"] == "skipped":
            skipped += 1
            continue

        asset_id = item.get("asset_id")
        if not asset_id:
            errors.append(f"No Immich asset for {Path(item['source_file']).name}")
            continue

        # Determine final values
        analysis = item["analysis"]
        if review["status"] == "corrected":
            date_str = review.get("corrected_date") or analysis["date_estimate"]
            desc_en = review.get("corrected_description_en") or analysis["description_en"]
            desc_zh = review.get("corrected_description_zh") or analysis["description_zh"]
        else:
            date_str = analysis["date_estimate"]
            desc_en = analysis["description_en"]
            desc_zh = analysis["description_zh"]

        desc = desc_en
        if desc_zh:
            desc = f"{desc}\n\n{desc_zh}"

        try:
            update_asset(
                client,
                asset_id,
                date_time_original=date_estimate_to_iso(date_str) if date_str else None,
                description=desc if desc else None,
            )
            pushed += 1
        except Exception as e:
            errors.append(f"{source_name}: {e}")

    return {"pushed": pushed, "skipped": skipped, "errors": errors}


# --- HTTP handler ---


class ReviewHandler(BaseHTTPRequestHandler):
    """Route dispatcher for the review dashboard API."""

    def log_message(self, format, *args):
        log.debug("HTTP %s", format % args)

    def _json_response(self, data: dict | list, status: int = 200):
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
        path = self.path.split("?")[0]

        if path == "/":
            self._serve_html()
        elif path == "/api/runs":
            self._json_response(list_runs())
        elif m := re.match(r"^/api/runs/([^/]+)/items$", path):
            self._json_response(get_run_items(m.group(1)))
        elif m := re.match(r"^/api/immich/thumbnail/([^/]+)$", path):
            self._proxy_thumbnail(m.group(1))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = self.path.split("?")[0]

        if m := re.match(r"^/api/runs/([^/]+)/items/([^/]+)/review$", path):
            self._save_review(m.group(1), m.group(2))
        elif m := re.match(r"^/api/runs/([^/]+)/push$", path):
            self._push_to_immich(m.group(1))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_html(self):
        if not HTML_PATH.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "review.html not found")
            return
        body = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_thumbnail(self, asset_id: str):
        """Proxy Immich thumbnail to avoid CORS / exposing API key."""
        try:
            url = config.IMMICH_URL.rstrip("/") + f"/api/assets/{asset_id}/thumbnail"
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
            log.warning("Thumbnail proxy failed for %s: %s", asset_id, e)
            self.send_error(HTTPStatus.BAD_GATEWAY, str(e))

    def _save_review(self, run_id: str, sha: str):
        try:
            body = json.loads(self._read_body())
            decision = ReviewDecision.model_validate(body)
            save_review(run_id, sha, decision)
            self._json_response({"ok": True, "sha": sha, "status": decision.status})
        except Exception as e:
            self._json_response({"error": str(e)}, status=400)

    def _push_to_immich(self, run_id: str):
        try:
            result = push_reviewed_to_immich(run_id)
            self._json_response(result)
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)


# --- Entry point ---


def main():
    config.setup_logging()
    log.info("Living Archive — Review Dashboard")
    log.info("  AI Layer: %s", config.AI_LAYER_DIR)
    log.info("  Starting server on http://0.0.0.0:%d", PORT)

    server = HTTPServer(("0.0.0.0", PORT), ReviewHandler)
    webbrowser.open(f"http://localhost:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
