"""Immich REST API client for asset updates and album management."""

import httpx

from . import config
from .config import retry

TIMEOUT = 30.0


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=config.IMMICH_URL.rstrip("/") + "/api",
        headers={"x-api-key": config.IMMICH_API_KEY},
        timeout=TIMEOUT,
    )


@retry()
def search_assets_by_path(client: httpx.Client, path_prefix: str) -> list[dict]:
    """Search for assets whose originalPath contains path_prefix.

    Uses POST /search/metadata with originalPath filter.
    Paginates through all results.
    """
    assets = []
    page = 1
    while True:
        resp = client.post(
            "/search/metadata",
            json={"originalPath": path_prefix, "page": page, "size": 250},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("assets", {}).get("items", [])
        if not items:
            break
        assets.extend(items)
        # If fewer items than page size, we're done
        if len(items) < 250:
            break
        page += 1
    return assets


def build_path_lookup(assets: list[dict]) -> dict[str, str]:
    """Build a mapping from originalPath filename -> assetId.

    Immich stores paths like /external/photos/2009 Scanned Media/1978/file.tiff
    We key by the filename portion for flexible matching.
    """
    lookup = {}
    for asset in assets:
        original_path = asset.get("originalPath", "")
        lookup[original_path] = asset["id"]
    return lookup


@retry()
def update_asset(
    client: httpx.Client,
    asset_id: str,
    date_time_original: str | None = None,
    description: str | None = None,
) -> None:
    """Update an asset's metadata via PUT /assets."""
    body: dict = {"ids": [asset_id]}
    if date_time_original:
        body["dateTimeOriginal"] = date_time_original
    if description:
        body["description"] = description
    resp = client.put("/assets", json=body)
    resp.raise_for_status()


@retry()
def create_album(
    client: httpx.Client,
    name: str,
    description: str = "",
    asset_ids: list[str] | None = None,
) -> dict:
    """Create an album, optionally with initial assets."""
    body: dict = {"albumName": name, "description": description}
    if asset_ids:
        body["assetIds"] = asset_ids
    resp = client.post("/albums", json=body)
    resp.raise_for_status()
    return resp.json()


def add_assets_to_album(
    client: httpx.Client, album_id: str, asset_ids: list[str]
) -> None:
    """Add assets to an existing album."""
    if not asset_ids:
        return
    resp = client.put(f"/albums/{album_id}/assets", json={"ids": asset_ids})
    resp.raise_for_status()


def date_estimate_to_iso(date_str: str) -> str:
    """Convert a date estimate like '1978-06' or '1978' to ISO datetime.

    Immich expects a full ISO datetime string for dateTimeOriginal.
    """
    parts = date_str.split("-")
    if len(parts) == 1:
        return f"{parts[0]}-01-01T00:00:00.000Z"
    elif len(parts) == 2:
        return f"{parts[0]}-{parts[1]}-01T00:00:00.000Z"
    else:
        return f"{date_str}T00:00:00.000Z"
