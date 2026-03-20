"""Curate test set from catalog.db for embedding experiments."""

import json
import sqlite3
import sys
from pathlib import Path

from . import config


# Desired distribution: (slice pattern, count, content_type)
PHOTO_SLICES = [
    ("2009 Scanned Media/1978%", 5, "1978 scans"),
    ("2009 Scanned Media/198%", 5, "1980-82 scans"),
    ("%Wedding%", 10, "Wedding album"),
    ("%Big_Red%", 5, "Big Red Album"),
    ("%Pink_Flower%", 5, "Pink Flower Album"),
    ("%Swei%Chi%", 5, "2022 Swei Chi"),
]
ASSORTED_COUNT = 5  # fill from remaining slices
DOCUMENT_COUNT = 10

# Preferred document types for diversity
DOC_TYPE_TARGETS = [
    "trust", "legal", "financial", "insurance", "letter",
    "certificate", "medical", "deed", "employment", "memorial",
]


def curate_test_set(catalog_db: Path) -> dict:
    """Select 50 assets from catalog.db. Returns locked-inputs structure."""
    conn = sqlite3.connect(str(catalog_db))
    conn.row_factory = sqlite3.Row

    photos = []
    used_shas = set()

    # Select photos by slice
    for pattern, count, label in PHOTO_SLICES:
        rows = conn.execute(
            """SELECT a.sha256, a.path, a.slice, a.manifest_path
               FROM assets a
               WHERE a.content_type = 'photo'
                 AND a.status = 'indexed'
                 AND a.manifest_path IS NOT NULL
                 AND a.slice LIKE ?
               ORDER BY RANDOM()
               LIMIT ?""",
            (pattern, count),
        ).fetchall()
        for r in rows:
            if r["sha256"] not in used_shas:
                photos.append({
                    "sha256": r["sha256"],
                    "content_type": "photo",
                    "source_path": r["path"],
                    "manifest_path": r["manifest_path"],
                    "slice": r["slice"],
                    "label": label,
                })
                used_shas.add(r["sha256"])

    # Fill assorted from remaining slices
    if len(photos) < 40:
        exclude_patterns = " AND ".join(
            f"a.slice NOT LIKE '{p}'" for p, _, _ in PHOTO_SLICES
        )
        remaining = 40 - len(photos)
        rows = conn.execute(
            f"""SELECT a.sha256, a.path, a.slice, a.manifest_path
                FROM assets a
                WHERE a.content_type = 'photo'
                  AND a.status = 'indexed'
                  AND a.manifest_path IS NOT NULL
                  AND {exclude_patterns}
                ORDER BY RANDOM()
                LIMIT ?""",
            (remaining,),
        ).fetchall()
        for r in rows:
            if r["sha256"] not in used_shas:
                photos.append({
                    "sha256": r["sha256"],
                    "content_type": "photo",
                    "source_path": r["path"],
                    "manifest_path": r["manifest_path"],
                    "slice": r["slice"],
                    "label": "assorted",
                })
                used_shas.add(r["sha256"])

    # Select documents — prefer diversity of document types
    documents = []
    for doc_type in DOC_TYPE_TARGETS:
        if len(documents) >= DOCUMENT_COUNT:
            break
        rows = conn.execute(
            """SELECT a.sha256, a.path, a.slice, a.manifest_path,
                      dq.document_type
               FROM assets a
               LEFT JOIN doc_quality dq ON a.sha256 = dq.sha256
               WHERE a.content_type = 'document'
                 AND a.status = 'indexed'
                 AND a.manifest_path IS NOT NULL
                 AND LOWER(COALESCE(dq.document_type, '')) LIKE ?
               ORDER BY RANDOM()
               LIMIT 1""",
            (f"%{doc_type}%",),
        ).fetchall()
        for r in rows:
            if r["sha256"] not in used_shas:
                documents.append({
                    "sha256": r["sha256"],
                    "content_type": "document",
                    "source_path": r["path"],
                    "manifest_path": r["manifest_path"],
                    "slice": r["slice"],
                    "document_type": r["document_type"],
                    "label": doc_type,
                })
                used_shas.add(r["sha256"])

    # Fill remaining document slots
    if len(documents) < DOCUMENT_COUNT:
        remaining = DOCUMENT_COUNT - len(documents)
        exclude = ",".join(f"'{s}'" for s in used_shas)
        rows = conn.execute(
            f"""SELECT a.sha256, a.path, a.slice, a.manifest_path,
                       dq.document_type
                FROM assets a
                LEFT JOIN doc_quality dq ON a.sha256 = dq.sha256
                WHERE a.content_type = 'document'
                  AND a.status = 'indexed'
                  AND a.manifest_path IS NOT NULL
                  AND a.sha256 NOT IN ({exclude})
                ORDER BY RANDOM()
                LIMIT ?""",
            (remaining,),
        ).fetchall()
        for r in rows:
            documents.append({
                "sha256": r["sha256"],
                "content_type": "document",
                "source_path": r["path"],
                "manifest_path": r["manifest_path"],
                "slice": r["slice"],
                "document_type": r["document_type"],
                "label": "other",
            })

    conn.close()

    return {
        "curated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "catalog_db": str(catalog_db),
        "photo_count": len(photos),
        "document_count": len(documents),
        "total": len(photos) + len(documents),
        "assets": photos + documents,
    }


def resolve_source_paths(locked_inputs: dict) -> dict:
    """Resolve relative source paths to absolute NAS paths."""
    for asset in locked_inputs["assets"]:
        path = asset["source_path"]
        if not Path(path).is_absolute():
            if asset["content_type"] == "photo":
                asset["source_path"] = str(config.MEDIA_ROOT / path)
            elif asset["content_type"] == "document":
                asset["source_path"] = str(config.DOCUMENTS_ROOT / path)
    return locked_inputs


def resolve_manifest_paths(locked_inputs: dict) -> dict:
    """Resolve relative manifest paths to absolute paths under data/."""
    for asset in locked_inputs["assets"]:
        mp = asset.get("manifest_path")
        if mp and not Path(mp).is_absolute():
            if asset["content_type"] == "photo":
                asset["manifest_path"] = str(config.DATA_DIR / "photos" / mp)
            elif asset["content_type"] == "document":
                asset["manifest_path"] = str(config.DATA_DIR / "documents" / mp)
    return locked_inputs


def validate_accessibility(locked_inputs: dict) -> dict:
    """Check which source files are accessible. Returns validation report."""
    report = {"accessible": 0, "missing": 0, "missing_files": []}
    for asset in locked_inputs["assets"]:
        src = Path(asset["source_path"])
        if src.exists():
            report["accessible"] += 1
        else:
            report["missing"] += 1
            report["missing_files"].append(str(src))
    return report


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "curate"

    if cmd == "curate":
        if not config.CATALOG_DB.exists():
            print(f"ERROR: catalog.db not found at {config.CATALOG_DB}")
            sys.exit(1)

        result = curate_test_set(config.CATALOG_DB)
        result = resolve_source_paths(result)
        result = resolve_manifest_paths(result)

        out_dir = config.RUNS_DIR / "p0-setup"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "locked-inputs.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(f"Curated {result['total']} assets "
              f"({result['photo_count']} photos, "
              f"{result['document_count']} documents)")
        print(f"Written to {out_path}")

        # Validate accessibility
        report = validate_accessibility(result)
        print(f"Accessible: {report['accessible']}, "
              f"Missing: {report['missing']}")
        if report["missing_files"]:
            print("Missing files:")
            for f in report["missing_files"][:5]:
                print(f"  {f}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
