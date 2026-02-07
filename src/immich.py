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


# --- People / Face APIs ---


@retry()
def list_people(client: httpx.Client, with_hidden: bool = False) -> list[dict]:
    """List all people (face clusters) from Immich, paginating through all pages."""
    people = []
    page = 1
    while True:
        resp = client.get("/people", params={"withHidden": with_hidden, "page": page})
        resp.raise_for_status()
        data = resp.json()
        items = data.get("people", [])
        if not items:
            break
        people.extend(items)
        if not data.get("hasNextPage", False):
            break
        page += 1
    return people


@retry()
def get_person(client: httpx.Client, person_id: str) -> dict:
    """Get a single person's details."""
    resp = client.get(f"/people/{person_id}")
    resp.raise_for_status()
    return resp.json()


@retry()
def get_person_statistics(client: httpx.Client, person_id: str) -> dict:
    """Get asset count for a person cluster."""
    resp = client.get(f"/people/{person_id}/statistics")
    resp.raise_for_status()
    return resp.json()


@retry()
def update_person(
    client: httpx.Client,
    person_id: str,
    name: str | None = None,
    birth_date: str | None = None,
) -> dict:
    """Update a person's name and/or birth date."""
    body: dict = {}
    if name is not None:
        body["name"] = name
    if birth_date is not None:
        body["birthDate"] = birth_date
    resp = client.put(f"/people/{person_id}", json=body)
    resp.raise_for_status()
    return resp.json()


@retry()
def merge_people(
    client: httpx.Client, target_person_id: str, source_person_ids: list[str]
) -> dict:
    """Merge source person clusters into target."""
    resp = client.post(
        f"/people/{target_person_id}/merge",
        json={"ids": source_person_ids},
    )
    resp.raise_for_status()
    return resp.json()


def get_person_thumbnail(client: httpx.Client, person_id: str) -> bytes:
    """Get the face crop thumbnail for a person cluster."""
    resp = client.get(f"/people/{person_id}/thumbnail")
    resp.raise_for_status()
    return resp.content


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
