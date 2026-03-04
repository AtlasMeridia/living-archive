"""Branch B — Fuzzy/phonetic matching dedup.

Applies Branch A string normalization, then groups clusters whose
phonetic signatures (Metaphone per token) overlap above a threshold.
Uses jellyfish for phonetic encoding and Jaro-Winkler for string similarity.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import jellyfish

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs" / "p1-person-branches"

# Import Branch A's normalizer
sys.path.insert(0, str(Path(__file__).resolve().parent))
from branch_a import normalize

# Thresholds
JARO_WINKLER_THRESHOLD = 0.85  # for comparing normalized full names
TOKEN_METAPHONE_MATCH_RATIO = 0.5  # fraction of tokens with matching metaphone


def phonetic_key(normalized_name: str) -> tuple[str, ...]:
    """Get metaphone codes for each token in a normalized name."""
    tokens = normalized_name.split()
    return tuple(jellyfish.metaphone(t) for t in tokens)


def names_are_similar(norm_a: str, norm_b: str) -> bool:
    """Check if two normalized names are phonetically similar enough to merge."""
    if norm_a == norm_b:
        return True

    # Jaro-Winkler on full normalized string
    jw = jellyfish.jaro_winkler_similarity(norm_a, norm_b)
    if jw >= JARO_WINKLER_THRESHOLD:
        return True

    # Token-level metaphone comparison
    tokens_a = norm_a.split()
    tokens_b = norm_b.split()

    # Only compare if token counts are close (within 1)
    if abs(len(tokens_a) - len(tokens_b)) > 1:
        return False

    meta_a = [jellyfish.metaphone(t) for t in tokens_a]
    meta_b = [jellyfish.metaphone(t) for t in tokens_b]

    # Count matching metaphone codes (order-sensitive, aligned by position)
    matches = 0
    for ma, mb in zip(meta_a, meta_b):
        if ma == mb:
            matches += 1

    max_tokens = max(len(meta_a), len(meta_b))
    if max_tokens > 0 and matches / max_tokens >= TOKEN_METAPHONE_MATCH_RATIO:
        return True

    return False


def merge_clusters(branch_a_clusters: dict[str, list[str]]) -> dict[str, list[str]]:
    """Take Branch A clusters and merge those with phonetic similarity."""
    keys = list(branch_a_clusters.keys())
    # Union-Find for merging
    parent = {k: k for k in keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Compare all pairs — O(n^2) but n is manageable (~900)
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if find(ka) != find(kb) and names_are_similar(ka, kb):
                union(ka, kb)

    # Group by root
    groups = defaultdict(set)
    for k in keys:
        root = find(k)
        for variant in branch_a_clusters[k]:
            groups[root].add(variant)

    return {k: sorted(v) for k, v in groups.items()}


def main():
    # Load Branch A results
    branch_a = json.loads((RUNS_DIR / "branch-a-clusters.json").read_text())

    # Reconstruct full cluster map (merged + singletons) from raw names
    raw = json.loads((RUNS_DIR / "raw-names.json").read_text())
    names = list(raw["names"].keys())

    # Rebuild Branch A clusters (all, not just merged)
    from branch_a import cluster as branch_a_cluster
    all_a_clusters = branch_a_cluster(names)

    # Merge phonetically
    merged = merge_clusters(all_a_clusters)

    # Separate multi-variant clusters from singletons
    multi = {k: v for k, v in merged.items() if len(v) > 1}
    singletons = {k: v for k, v in merged.items() if len(v) == 1}

    result = {
        "branch": "B",
        "method": "fuzzy_phonetic",
        "input_count": len(names),
        "cluster_count": len(merged),
        "merged_cluster_count": len(multi),
        "singleton_count": len(singletons),
        "largest_cluster_size": max(len(v) for v in merged.values()),
        "jaro_winkler_threshold": JARO_WINKLER_THRESHOLD,
        "token_metaphone_ratio": TOKEN_METAPHONE_MATCH_RATIO,
        "merged_clusters": multi,
    }

    out = RUNS_DIR / "branch-b-clusters.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Branch B: {len(merged)} clusters ({len(multi)} merged, {len(singletons)} singletons)")
    print(f"Largest cluster: {max(len(v) for v in merged.values())} variants")
    print(f"Output: {out}")

    # Print merged clusters for review
    print("\n--- Merged clusters (phonetic) ---")
    for key, variants in sorted(multi.items(), key=lambda x: -len(x[1])):
        print(f"\n  [{key}] ({len(variants)} variants):")
        for v in variants:
            print(f"    - {v}")


if __name__ == "__main__":
    main()
