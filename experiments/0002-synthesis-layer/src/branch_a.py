"""Branch A — String normalization dedup.

Deterministic rules: lowercase, strip hyphens, collapse whitespace,
strip parenthetical annotations, normalize common patterns.
Group by exact normalized string.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs" / "p1-person-branches"


def normalize(name: str) -> str:
    """Normalize a name string for dedup grouping."""
    s = name.strip()
    # Strip parenthetical annotations: "(father)", "(劉逢光)", "(deceased)", etc.
    s = re.sub(r"\s*\([^)]*\)", "", s)
    # Strip suffixes like "MD", "M.D.", "Jr.", "III", "CFP", "MA"
    s = re.sub(r",?\s+(MD|M\.D\.|Jr\.?|III|CFP|MA|RBM|JMK)\.?\s*$", "", s, flags=re.IGNORECASE)
    # Strip honorifics: "Dr.", "Mr.", "Mrs.", "Ms.", "Rev.", "Elder", "Col"
    s = re.sub(r"^(Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Rev\.?|Elder|Col)\s+", "", s, flags=re.IGNORECASE)
    # Lowercase
    s = s.lower()
    # Strip hyphens and periods (Feng-Kuang -> feng kuang, F.K. -> fk)
    s = s.replace("-", " ").replace(".", " ")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cluster(names: list[str]) -> dict[str, list[str]]:
    """Group names by normalized form. Returns {canonical: [variants]}."""
    groups = defaultdict(list)
    for name in names:
        key = normalize(name)
        if key:
            groups[key].append(name)
    # Deduplicate variant lists
    return {k: sorted(set(v)) for k, v in groups.items()}


def main():
    raw = json.loads((RUNS_DIR / "raw-names.json").read_text())
    names = list(raw["names"].keys())

    clusters = cluster(names)

    # Only keep clusters with >1 variant (actual merges)
    merged = {k: v for k, v in clusters.items() if len(v) > 1}
    singletons = {k: v for k, v in clusters.items() if len(v) == 1}

    result = {
        "branch": "A",
        "method": "string_normalization",
        "input_count": len(names),
        "cluster_count": len(clusters),
        "merged_cluster_count": len(merged),
        "singleton_count": len(singletons),
        "largest_cluster_size": max(len(v) for v in clusters.values()),
        "merged_clusters": merged,
    }

    out = RUNS_DIR / "branch-a-clusters.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Branch A: {len(clusters)} clusters ({len(merged)} merged, {len(singletons)} singletons)")
    print(f"Largest cluster: {max(len(v) for v in clusters.values())} variants")
    print(f"Output: {out}")

    # Print merged clusters for review
    print("\n--- Merged clusters ---")
    for key, variants in sorted(merged.items(), key=lambda x: -len(x[1])):
        print(f"\n  [{key}] ({len(variants)} variants):")
        for v in variants:
            print(f"    - {v}")


if __name__ == "__main__":
    main()
