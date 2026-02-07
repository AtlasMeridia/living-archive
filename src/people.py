"""People registry: durable identity store independent of Immich.

Registry lives at: _ai-layer/people/registry.json
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import PeopleRegistry, Person

log = logging.getLogger("living_archive")

PEOPLE_DIR = config.AI_LAYER_DIR / "people"
REGISTRY_PATH = PEOPLE_DIR / "registry.json"


def load_registry() -> PeopleRegistry:
    """Load the people registry from disk. Returns empty registry if missing."""
    if not REGISTRY_PATH.exists():
        return PeopleRegistry()
    data = json.loads(REGISTRY_PATH.read_text())
    return PeopleRegistry.model_validate(data)


def save_registry(registry: PeopleRegistry) -> Path:
    """Atomically write the people registry to disk."""
    PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry.model_dump(), indent=2, ensure_ascii=False))
    tmp.rename(REGISTRY_PATH)
    return REGISTRY_PATH


def add_person(
    registry: PeopleRegistry,
    name_en: str,
    name_zh: str = "",
    relationship: str = "",
    birth_year: int | None = None,
    notes: str = "",
    immich_person_ids: list[str] | None = None,
) -> Person:
    """Add a new person to the registry. Returns the created Person."""
    now = datetime.now(timezone.utc).isoformat()
    person = Person(
        person_id=str(uuid.uuid4()),
        name_en=name_en,
        name_zh=name_zh,
        relationship=relationship,
        birth_year=birth_year,
        notes=notes,
        immich_person_ids=immich_person_ids or [],
        created_at=now,
        updated_at=now,
    )
    registry.people.append(person)
    return person


def find_person_by_immich_id(
    registry: PeopleRegistry, immich_person_id: str
) -> Person | None:
    """Find a person by their linked Immich face cluster ID."""
    for person in registry.people:
        if immich_person_id in person.immich_person_ids:
            return person
    return None


def find_person_by_name(
    registry: PeopleRegistry, name: str
) -> Person | None:
    """Find a person by English or Chinese name (case-insensitive for EN)."""
    for person in registry.people:
        if person.name_en.lower() == name.lower() or person.name_zh == name:
            return person
    return None


def link_immich_cluster(
    registry: PeopleRegistry, person_id: str, immich_person_id: str
) -> bool:
    """Link an Immich face cluster ID to an existing person. Returns True if found."""
    for person in registry.people:
        if person.person_id == person_id:
            if immich_person_id not in person.immich_person_ids:
                person.immich_person_ids.append(immich_person_id)
                person.updated_at = datetime.now(timezone.utc).isoformat()
            return True
    return False
