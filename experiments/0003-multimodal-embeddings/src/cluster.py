"""Phase 4: Embedding cluster analysis vs. synthesis entities."""

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

from . import config, vecdb


def load_image_embeddings(db_path: Path) -> tuple[list[str], np.ndarray]:
    """Load all image embeddings as a matrix. Returns (sha256s, matrix)."""
    conn = vecdb.connect(db_path)
    rows = list(conn.execute("SELECT sha256, embedding FROM vec_images"))
    conn.close()

    if not rows:
        return [], np.array([])

    sha256s = [r[0] for r in rows]
    matrix = np.array([
        np.frombuffer(r[1], dtype=np.float32) for r in rows
    ])
    return sha256s, matrix


def cluster_kmeans(matrix: np.ndarray, n_clusters: int = 5) -> np.ndarray:
    """K-means clustering. Returns cluster labels."""
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    return km.fit_predict(matrix)


def cluster_hdbscan(matrix: np.ndarray, min_cluster_size: int = 3) -> np.ndarray:
    """HDBSCAN clustering. Returns cluster labels (-1 = noise)."""
    from sklearn.cluster import HDBSCAN
    hdb = HDBSCAN(min_cluster_size=min_cluster_size, metric="cosine")
    return hdb.fit_predict(matrix)


def label_clusters(
    sha256s: list[str],
    labels: np.ndarray,
    db_path: Path,
) -> list[dict]:
    """Label each cluster by inspecting member manifests."""
    conn = vecdb.connect(db_path)
    clusters = {}

    for sha, label in zip(sha256s, labels):
        label = int(label)
        if label not in clusters:
            clusters[label] = []
        meta_rows = list(conn.execute(
            "SELECT source_path, manifest_path FROM embedded_assets "
            "WHERE sha256 = ?", (sha,)
        ))
        clusters[label].append({
            "sha256": sha,
            "source_path": meta_rows[0][0] if meta_rows else None,
            "manifest_path": meta_rows[0][1] if meta_rows else None,
        })

    conn.close()

    result = []
    for label in sorted(clusters.keys()):
        members = clusters[label]
        # Try to extract tags/descriptions from manifests
        tags_seen = {}
        for m in members:
            if m["manifest_path"]:
                mp = Path(m["manifest_path"])
                if mp.exists():
                    try:
                        manifest = json.loads(mp.read_text())
                        for tag in manifest.get("analysis", {}).get("tags", []):
                            tags_seen[tag] = tags_seen.get(tag, 0) + 1
                    except Exception:
                        pass

        top_tags = sorted(tags_seen.items(), key=lambda x: -x[1])[:5]
        result.append({
            "cluster_id": label,
            "size": len(members),
            "top_tags": [t[0] for t in top_tags],
            "members": members,
        })

    return result


def compare_with_synthesis(
    cluster_results: list[dict],
    synthesis_db_path: Path,
) -> dict:
    """Compare embedding clusters with synthesis entity groupings."""
    comparison = {
        "embedding_clusters": len(cluster_results),
        "overlaps": [],
    }

    if not synthesis_db_path.exists():
        comparison["note"] = "synthesis.db not found, skipping comparison"
        return comparison

    conn = sqlite3.connect(str(synthesis_db_path))
    conn.row_factory = sqlite3.Row

    # Get entity-asset groupings from synthesis
    try:
        entity_groups = conn.execute(
            """SELECT e.entity_value, GROUP_CONCAT(ea.asset_sha256) as assets
               FROM entities e
               JOIN entity_assets ea ON e.entity_id = ea.entity_id
               WHERE e.entity_type = 'person'
               GROUP BY e.entity_value"""
        ).fetchall()
    except Exception:
        entity_groups = []

    conn.close()

    synth_groups = {}
    for eg in entity_groups:
        assets = set(eg["assets"].split(",")) if eg["assets"] else set()
        if len(assets) > 1:
            synth_groups[eg["entity_value"]] = assets

    # Check overlap between embedding clusters and synthesis groups
    for cluster in cluster_results:
        cluster_shas = {m["sha256"] for m in cluster["members"]}
        for entity_name, entity_shas in synth_groups.items():
            overlap = cluster_shas & entity_shas
            if overlap:
                comparison["overlaps"].append({
                    "cluster_id": cluster["cluster_id"],
                    "entity": entity_name,
                    "cluster_size": cluster["size"],
                    "entity_size": len(entity_shas),
                    "overlap_size": len(overlap),
                })

    comparison["synthesis_entity_groups"] = len(synth_groups)
    return comparison


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "run":
        if not config.EMBEDDINGS_DB.exists():
            print("ERROR: embeddings.db not found.")
            sys.exit(1)

        out_dir = config.RUNS_DIR / "p4-clusters"
        out_dir.mkdir(parents=True, exist_ok=True)

        sha256s, matrix = load_image_embeddings(config.EMBEDDINGS_DB)
        if len(sha256s) < 3:
            print(f"Only {len(sha256s)} embeddings — need at least 3.")
            sys.exit(1)

        print(f"Loaded {len(sha256s)} image embeddings ({matrix.shape})")

        # K-means
        n_clusters = min(5, len(sha256s) // 2)
        km_labels = cluster_kmeans(matrix, n_clusters=n_clusters)
        km_clusters = label_clusters(sha256s, km_labels, config.EMBEDDINGS_DB)
        print(f"K-means: {n_clusters} clusters")
        for c in km_clusters:
            print(f"  Cluster {c['cluster_id']}: {c['size']} members, "
                  f"tags={c['top_tags']}")

        # HDBSCAN
        hdb_labels = cluster_hdbscan(matrix)
        hdb_clusters = label_clusters(sha256s, hdb_labels, config.EMBEDDINGS_DB)
        n_noise = sum(1 for l in hdb_labels if l == -1)
        print(f"HDBSCAN: {len(hdb_clusters)} clusters "
              f"({n_noise} noise points)")
        for c in hdb_clusters:
            print(f"  Cluster {c['cluster_id']}: {c['size']} members, "
                  f"tags={c['top_tags']}")

        # Compare with synthesis
        comparison = compare_with_synthesis(km_clusters, config.SYNTHESIS_DB)

        analysis = {
            "kmeans": {"n_clusters": n_clusters, "clusters": km_clusters},
            "hdbscan": {
                "clusters": hdb_clusters,
                "noise_points": n_noise,
            },
            "synthesis_comparison": comparison,
        }
        (out_dir / "cluster-analysis.json").write_text(
            json.dumps(analysis, indent=2, default=str))
        print(f"\nSaved to {out_dir}/cluster-analysis.json")

    else:
        print("Usage: python -m ...cluster run")
        sys.exit(1)
