"""Sync people between Immich face clusters and the AI layer registry.

Pull: Import unnamed Immich clusters into the registry for identification.
Push: Apply names from the registry back to Immich.
Queue: Generate prioritized unknown-face list for naming sessions.
Import: Apply elder-session naming updates from queue CSV back to registry.

Run: python -m src.sync_people [pull|push|status|queue|import-csv]
"""

import csv
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .immich import (
    _client as immich_client,
    get_person_statistics,
    list_people,
    update_person,
)
from .people import (
    REGISTRY_PATH,
    add_person,
    find_person_by_immich_id,
    load_registry,
    save_registry,
)

log = config.setup_logging()

# Only import clusters with at least this many assets
MIN_ASSETS_FOR_IMPORT = 3
DEFAULT_QUEUE_LIMIT = 50
DEFAULT_QUEUE_CSV = config.DATA_DIR / "people" / "identification_queue.csv"


def _is_named(person) -> bool:
    """True if person has either English or Chinese name."""
    return bool(person.name_en.strip() or person.name_zh.strip())


def _asset_hint_from_notes(notes: str) -> int:
    """Extract '(N assets)' hint from auto-import notes."""
    match = re.search(r"\((\d+)\s+assets\)", notes or "")
    return int(match.group(1)) if match else 0


def _queue_rows(registry, include_named: bool = False) -> list[dict]:
    """Build and sort a naming queue from registry data."""
    rows = []
    for person in registry.people:
        if not include_named and _is_named(person):
            continue
        rows.append({
            "person_id": person.person_id,
            "name_en": person.name_en,
            "name_zh": person.name_zh,
            "relationship": person.relationship,
            "asset_count_hint": _asset_hint_from_notes(person.notes),
            "immich_person_id": person.immich_person_ids[0] if person.immich_person_ids else "",
            "notes": person.notes,
        })
    rows.sort(
        key=lambda r: (
            1 if (r["name_en"] or r["name_zh"]) else 0,
            -(r["asset_count_hint"] or 0),
            (r["name_en"] or r["name_zh"] or "").lower(),
            r["person_id"],
        )
    )
    return rows


def _parse_birth_year(raw: str) -> int | None:
    """Parse birth year from CSV field."""
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _apply_csv_row(person, row: dict[str, str]) -> list[str]:
    """Apply non-empty CSV row fields to a person; return changed field names."""
    changed_fields: list[str] = []

    for field in ("name_en", "name_zh", "relationship", "notes"):
        raw_value = row.get(field, "")
        new_value = raw_value.strip()
        if new_value and getattr(person, field) != new_value:
            setattr(person, field, new_value)
            changed_fields.append(field)

    birth_year = _parse_birth_year(row.get("birth_year", ""))
    if birth_year is not None and person.birth_year != birth_year:
        person.birth_year = birth_year
        changed_fields.append("birth_year")

    if changed_fields:
        person.updated_at = datetime.now(timezone.utc).isoformat()
    return changed_fields


def cmd_status():
    """Show current state of people in both Immich and the registry."""
    log.info("People Sync — Status")
    log.info("")

    # Registry
    registry = load_registry()
    log.info("Registry: %s", REGISTRY_PATH)
    log.info("  People: %d", len(registry.people))
    named = [p for p in registry.people if p.name_en]
    unnamed = [p for p in registry.people if not p.name_en]
    log.info("  Named: %d", len(named))
    log.info("  Unnamed: %d", len(unnamed))
    linked = [p for p in registry.people if p.immich_person_ids]
    log.info("  Linked to Immich: %d", len(linked))
    log.info("")

    # Immich
    immich_errors = config.validate_immich_config()
    if immich_errors:
        log.warning("Immich not configured: %s", immich_errors)
        return

    client = immich_client()
    people = list_people(client)
    immich_named = [p for p in people if p.get("name")]
    log.info("Immich:")
    log.info("  Face clusters: %d", len(people))
    log.info("  Named: %d", len(immich_named))
    log.info("  Unnamed: %d", len(people) - len(immich_named))
    for p in immich_named[:20]:
        log.info("    %s — %s", p["name"], p["id"][:8])


def cmd_pull():
    """Pull Immich face clusters into the registry.

    Imports clusters that have >= MIN_ASSETS_FOR_IMPORT assets and
    aren't already linked to a registry person.
    """
    log.info("People Sync — Pull from Immich")
    log.info("")

    client = immich_client()
    registry = load_registry()

    people = list_people(client)
    log.info("  Immich clusters: %d", len(people))

    imported = 0
    skipped_small = 0
    skipped_linked = 0

    for p in people:
        pid = p["id"]

        # Skip if already linked
        if find_person_by_immich_id(registry, pid):
            skipped_linked += 1
            continue

        # Skip small clusters (likely noise)
        stats = get_person_statistics(client, pid)
        asset_count = stats.get("assets", 0)
        if asset_count < MIN_ASSETS_FOR_IMPORT:
            skipped_small += 1
            continue

        # Import: use Immich name if one exists, otherwise leave blank
        name = p.get("name", "")
        person = add_person(
            registry,
            name_en=name,
            immich_person_ids=[pid],
            notes=f"Auto-imported from Immich ({asset_count} assets)",
        )
        imported += 1
        label = name if name else "(unnamed)"
        log.info("  Imported: %s — %d assets [%s]", label, asset_count, person.person_id[:8])

    save_registry(registry)
    log.info("")
    log.info("  Imported: %d", imported)
    log.info("  Skipped (already linked): %d", skipped_linked)
    log.info("  Skipped (< %d assets): %d", MIN_ASSETS_FOR_IMPORT, skipped_small)
    log.info("  Registry now has %d people", len(registry.people))


def cmd_push():
    """Push named people from the registry to Immich.

    Updates Immich person names for clusters linked in the registry.
    Only pushes if the registry person has a name and the Immich cluster
    is currently unnamed (won't overwrite manual Immich edits).
    """
    log.info("People Sync — Push to Immich")
    log.info("")

    client = immich_client()
    registry = load_registry()

    pushed = 0
    skipped = 0

    for person in registry.people:
        if not person.name_en:
            continue
        for immich_id in person.immich_person_ids:
            try:
                update_person(client, immich_id, name=person.name_en)
                pushed += 1
                log.info("  Pushed: %s -> %s", person.name_en, immich_id[:8])
            except Exception as e:
                skipped += 1
                log.warning("  Failed: %s -> %s: %s", person.name_en, immich_id[:8], e)

    log.info("")
    log.info("  Pushed: %d", pushed)
    log.info("  Failed: %d", skipped)


def cmd_queue(args: list[str]):
    """Print and optionally export a prioritized people naming queue.

    Defaults:
    - unnamed people only
    - top 50
    - no file output (use --csv to export)
    """
    limit = DEFAULT_QUEUE_LIMIT
    include_named = False
    out_csv: Path | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--include-named":
            include_named = True
            i += 1
            continue
        if arg == "--limit":
            if i + 1 >= len(args):
                log.error("Missing value for --limit")
                sys.exit(1)
            try:
                limit = max(1, int(args[i + 1]))
            except ValueError:
                log.error("Invalid --limit value: %s", args[i + 1])
                sys.exit(1)
            i += 2
            continue
        if arg == "--csv":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                out_csv = Path(args[i + 1])
                i += 2
            else:
                out_csv = DEFAULT_QUEUE_CSV
                i += 1
            continue
        if arg.isdigit():
            limit = max(1, int(arg))
            i += 1
            continue

        log.error("Unknown argument: %s", arg)
        log.info("Usage: python -m src.sync_people queue [limit|--limit N] [--csv [PATH]] [--include-named]")
        sys.exit(1)

    registry = load_registry()
    rows = _queue_rows(registry, include_named=include_named)[:limit]

    log.info("People Sync — Naming Queue")
    log.info("")
    log.info("  Registry: %s", REGISTRY_PATH)
    log.info("  Queue rows: %d", len(rows))
    log.info("  Include named: %s", include_named)
    log.info("")

    if not rows:
        log.info("  No people matched queue filters.")
        return

    for idx, row in enumerate(rows, start=1):
        label = row["name_en"] or row["name_zh"] or "(unknown)"
        assets = row["asset_count_hint"]
        assets_text = f"~{assets}" if assets else "?"
        person_short = row["person_id"][:8]
        immich_short = row["immich_person_id"][:8] if row["immich_person_id"] else "-"
        log.info(
            "  %3d. %-20s assets=%-5s person=%s immich=%s",
            idx, label, assets_text, person_short, immich_short,
        )

    if out_csv is not None:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "person_id",
                    "name_en",
                    "name_zh",
                    "relationship",
                    "asset_count_hint",
                    "immich_person_id",
                    "notes",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        log.info("")
        log.info("  Wrote CSV: %s", out_csv)


def cmd_import_csv(args: list[str]):
    """Apply naming updates from a queue CSV into registry.json.

    Expected columns include:
    person_id,name_en,name_zh,relationship,birth_year,notes
    """
    csv_path = DEFAULT_QUEUE_CSV
    dry_run = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--dry-run":
            dry_run = True
            i += 1
            continue
        if arg == "--csv":
            if i + 1 >= len(args):
                log.error("Missing value for --csv")
                sys.exit(1)
            csv_path = Path(args[i + 1])
            i += 2
            continue
        if arg.startswith("--"):
            log.error("Unknown argument: %s", arg)
            log.info("Usage: python -m src.sync_people import-csv [PATH|--csv PATH] [--dry-run]")
            sys.exit(1)
        csv_path = Path(arg)
        i += 1

    if not csv_path.exists():
        log.error("CSV not found: %s", csv_path)
        sys.exit(1)

    registry = load_registry()
    by_id = {p.person_id: p for p in registry.people}
    updated = 0
    missing = 0
    unchanged = 0

    log.info("People Sync — Import CSV")
    log.info("")
    log.info("  Registry: %s", REGISTRY_PATH)
    log.info("  CSV: %s", csv_path)
    log.info("  Dry run: %s", dry_run)
    log.info("")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            person_id = (row.get("person_id", "") or "").strip()
            if not person_id:
                continue

            person = by_id.get(person_id)
            if person is None:
                missing += 1
                log.warning("  Missing person_id in registry: %s", person_id)
                continue

            changed_fields = _apply_csv_row(person, row)
            if changed_fields:
                updated += 1
                label = person.name_en or person.name_zh or "(unknown)"
                log.info(
                    "  Updated %s (%s): %s",
                    person_id[:8],
                    label,
                    ", ".join(changed_fields),
                )
            else:
                unchanged += 1

    if updated > 0 and not dry_run:
        save_registry(registry)
        log.info("")
        log.info("  Saved registry updates.")

    log.info("")
    log.info("  Updated: %d", updated)
    log.info("  Unchanged: %d", unchanged)
    log.info("  Missing IDs: %d", missing)
    if dry_run:
        log.info("  Dry run only — no file changes written.")


def main():
    commands = {"status": cmd_status, "pull": cmd_pull, "push": cmd_push}
    if len(sys.argv) < 2:
        log.info("Usage: python -m src.sync_people [status|pull|push|queue|import-csv]")
        log.info("")
        log.info("  status  — Show people counts in registry and Immich")
        log.info("  pull    — Import Immich face clusters into registry")
        log.info("  push    — Apply registry names to Immich clusters")
        log.info("  queue   — Show naming queue (top unknown clusters by size)")
        log.info("  import-csv — Apply naming updates from queue CSV")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "queue":
        cmd_queue(sys.argv[2:])
        return
    if cmd == "import-csv":
        cmd_import_csv(sys.argv[2:])
        return
    if cmd not in commands:
        log.info("Usage: python -m src.sync_people [status|pull|push|queue|import-csv]")
        sys.exit(1)
    commands[cmd]()


if __name__ == "__main__":
    main()
