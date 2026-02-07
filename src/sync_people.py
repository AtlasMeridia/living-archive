"""Sync people between Immich face clusters and the AI layer registry.

Pull: Import unnamed Immich clusters into the registry for identification.
Push: Apply names from the registry back to Immich.

Run: python -m src.sync_people [pull|push|status]
"""

import logging
import sys

from . import config
from .immich import (
    _client as immich_client,
    get_person_statistics,
    list_people,
    update_person,
)
from .people import (
    add_person,
    find_person_by_immich_id,
    load_registry,
    save_registry,
)

log = config.setup_logging()

# Only import clusters with at least this many assets
MIN_ASSETS_FOR_IMPORT = 3


def cmd_status():
    """Show current state of people in both Immich and the registry."""
    log.info("People Sync — Status")
    log.info("")

    # Registry
    registry = load_registry()
    log.info("Registry: %s", config.AI_LAYER_DIR / "people" / "registry.json")
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


def main():
    commands = {"status": cmd_status, "pull": cmd_pull, "push": cmd_push}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        log.info("Usage: python -m src.sync_people [status|pull|push]")
        log.info("")
        log.info("  status  — Show people counts in registry and Immich")
        log.info("  pull    — Import Immich face clusters into registry")
        log.info("  push    — Apply registry names to Immich clusters")
        sys.exit(1)

    commands[sys.argv[1]]()


if __name__ == "__main__":
    main()
