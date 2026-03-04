"""Audit photo tags against prose descriptions to find under-tagging gaps.

Scans every photo manifest under data/photos/runs/*/manifests/ and checks
whether description_en, people_notes, and other prose fields describe concepts
the tags fail to capture. Reports:
  - Per-concept gap rates (e.g. prose says "mother and child" but no parent-child tag)
  - Photos with the most missing tags

Ported from haptic/scripts/audit_tags.py in naked-robot — same concept-definition
pattern, adapted for photo metadata categories.

Usage:
    python -m src.audit_tags
    python -m src.audit_tags --verbose   # list every gap
    python -m src.audit_tags --json      # machine-readable output
"""

import json
import re
import sys

from . import config

# ── Concept definitions ──────────────────────────────────────
#
# Each concept: prose patterns → expected tag(s) that should exist.
# Patterns match against combined prose (description_en + people_notes +
# location_estimate). Concept categories chosen for LA domain: family photos
# with relationship, condition, activity, and setting metadata gaps.

CONCEPTS = {
    "relationship/family": {
        "prose": [
            r"\bparent\w*\b", r"\bmother\b", r"\bmom\b", r"\bfather\b", r"\bdad\b",
            r"\bchild(?:ren)?\b", r"\bdaughter\b", r"\bson\b", r"\bsiblings?\b",
            r"\bbrother\b", r"\bsister\b", r"\bgrandmother\b", r"\bgrandfather\b",
            r"\bgrandparent\w*\b", r"\bcouple\b", r"\bhusband\b", r"\bwife\b",
            r"\bspouse\b", r"\bfamily\b", r"\belderly\b", r"\belder\w*\b",
        ],
        "tags": ["family", "parent-child", "couple", "siblings", "grandparent",
                 "elder-youth", "mother", "father", "together", "portrait"],
    },
    "condition/damage": {
        "prose": [
            r"\bfaded\b", r"\btorn\b", r"\bdamage\w*\b", r"\bwater.?damaged\b",
            r"\boverexposed\b", r"\bunderexposed\b", r"\bblurry\b",
            r"\bout.?of.?focus\b", r"\bcracked?\b", r"\bcreased?\b",
            r"\bdiscolou?red\b", r"\bscratched?\b", r"\bstained?\b",
            r"\bworn\b", r"\bdeteriorate\w*\b",
        ],
        "tags": ["faded", "torn", "damaged", "water-damaged", "overexposed",
                 "blurry", "poor-condition", "cracked", "vintage-damage"],
    },
    "activity/event": {
        "prose": [
            r"\bdining\b", r"\beating\b", r"\bmeal\b", r"\bcelebrat\w*\b",
            r"\bwedding\b", r"\bgraduat\w*\b", r"\bbirthday\b", r"\bceremony\b",
            r"\bparty\b", r"\bholiday\b", r"\bvacation\b", r"\btravel\w*\b",
            r"\btrip\b", r"\bgather\w*\b", r"\breunion\b", r"\bpicnic\b",
        ],
        "tags": ["dining", "celebration", "wedding", "graduation", "birthday",
                 "ceremony", "travel", "gathering", "holiday", "event"],
    },
    "group/crowd": {
        "prose": [
            r"\bgroup\b", r"\bcrowd\b", r"\bgathered\b",
            r"\bmultiple\s+people\b", r"\bseveral\s+people\b",
            r"\bsurrounded\b", r"\btogether\b",
        ],
        "tags": ["group", "crowd", "group-portrait", "gathering", "together",
                 "multiple-people"],
    },
    "setting/outdoor": {
        "prose": [
            r"\boutdoors?\b", r"\boutside\b", r"\bgarden\b", r"\bpark\b",
            r"\bbeach\b", r"\bmountain\w*\b", r"\bstreet\b", r"\byard\b",
            r"\bbackyard\b", r"\bfield\b", r"\bforest\b", r"\bnature\b",
        ],
        "tags": ["outdoor", "garden", "park", "beach", "street", "nature",
                 "landscape"],
    },
    "setting/indoor": {
        "prose": [
            r"\bindoors?\b", r"\binside\b", r"\bhome\b", r"\bhouse\b",
            r"\bkitchen\b", r"\bliving\s+room\b", r"\bbedroom\b",
            r"\bdining\s+room\b", r"\brestaurant\b", r"\boffice\b",
        ],
        "tags": ["indoor", "home", "kitchen", "restaurant", "office"],
    },
    "era/format": {
        "prose": [
            r"\bblack.and.white\b", r"\bblack\s+and\s+white\b",
            r"\bmonochrome\b", r"\bsepia\b", r"\bvintage\b",
            r"\bcolor\s+photo\b", r"\bpolaroid\b",
        ],
        "tags": ["black-and-white", "monochrome", "sepia", "vintage", "color",
                 "polaroid"],
    },
}


def build_prose(manifest: dict) -> str:
    """Concatenate prose fields into a single searchable string."""
    analysis = manifest.get("analysis", {})
    fields = ["description_en", "people_notes", "location_estimate", "ocr_text"]
    return " ".join((analysis.get(f) or "") for f in fields).lower()


def audit_photo(manifest: dict) -> list[dict]:
    """Return list of concept gaps for one photo."""
    prose = build_prose(manifest)
    analysis = manifest.get("analysis", {})
    tags = set(t.lower() for t in (analysis.get("tags") or []))
    gaps = []

    for concept, defn in CONCEPTS.items():
        matched_pattern = None
        for pat in defn["prose"]:
            m = re.search(pat, prose, re.IGNORECASE)
            if m:
                matched_pattern = m.group()
                break
        if not matched_pattern:
            continue

        has_tag = any(t in tags for t in defn["tags"])
        if not has_tag:
            gaps.append({
                "concept": concept,
                "matched": matched_pattern,
                "expected_tags": defn["tags"][:3],
            })

    return gaps


def load_manifests() -> list[dict]:
    """Load all photo manifests from data/photos/runs/*/manifests/."""
    runs_dir = config.AI_LAYER_DIR / "runs"
    manifests = []
    if not runs_dir.exists():
        return manifests
    for mf in sorted(runs_dir.glob("*/manifests/*.json")):
        try:
            manifest = json.loads(mf.read_text())
            manifest["_file"] = str(mf.relative_to(config.AI_LAYER_DIR))
            manifests.append(manifest)
        except (json.JSONDecodeError, OSError):
            pass
    return manifests


def main():
    verbose = "--verbose" in sys.argv
    as_json = "--json" in sys.argv

    manifests = load_manifests()
    if not manifests:
        print("No photo manifests found. Run the photo pipeline first.")
        return

    concept_gaps: dict[str, list[dict]] = {c: [] for c in CONCEPTS}
    photo_gaps: list[tuple[str, list[dict]]] = []

    for m in manifests:
        gaps = audit_photo(m)
        if gaps:
            source = m.get("source_file", m.get("_file", ""))
            photo_gaps.append((source, gaps))
            for g in gaps:
                concept_gaps[g["concept"]].append({
                    "file": source,
                    "matched": g["matched"],
                })

    if as_json:
        print(json.dumps({
            "total_photos": len(manifests),
            "photos_with_gaps": len(photo_gaps),
            "concepts": {
                c: {"gap_count": len(gaps), "examples": gaps[:5]}
                for c, gaps in concept_gaps.items() if gaps
            },
        }, indent=2))
        return

    print(f"Audited {len(manifests)} photos\n")
    print("CONCEPT GAP RATES")
    print("-" * 70)
    for concept, defn in CONCEPTS.items():
        mention_count = sum(
            1 for m in manifests
            if any(re.search(p, build_prose(m), re.IGNORECASE) for p in defn["prose"])
        )
        gap_count = len(concept_gaps[concept])
        tagged_count = mention_count - gap_count
        rate = (gap_count / mention_count * 100) if mention_count else 0
        print(f"  {concept:<25s}  {mention_count:4d} mentioned  "
              f"{tagged_count:4d} tagged  {gap_count:4d} missing  ({rate:.0f}% gap)")

    print()
    photo_gaps.sort(key=lambda x: -len(x[1]))
    top = photo_gaps[:15]
    if top:
        print(f"PHOTOS WITH MOST GAPS (top {len(top)})")
        print("-" * 70)
        for source, gaps in top:
            concepts = ", ".join(g["concept"] for g in gaps)
            print(f"  {source}")
            print(f"    missing: {concepts}")
        print()

    if verbose:
        print("ALL GAPS")
        print("-" * 70)
        for concept, gaps in concept_gaps.items():
            if not gaps:
                continue
            print(f"\n  {concept} ({len(gaps)} gaps):")
            for g in gaps:
                print(f"    {g['file']}  matched: \"{g['matched']}\"")

    total_gaps = sum(len(g) for g in concept_gaps.values())
    print(f"\nSummary: {total_gaps} tag gaps across "
          f"{len(photo_gaps)}/{len(manifests)} photos")


if __name__ == "__main__":
    main()
