"""Retrieval quality evaluation — precision@k, nDCG, cross-modal scoring."""

import json
import math
import sys
import time
from pathlib import Path

from . import config, embed, vecdb

# --- Phase 2 queries ---

TEXT_QUERIES = [
    "family dinner",
    "wedding ceremony",
    "children playing outdoors",
    "formal portrait",
    "Taiwan landscape",
    "grandmother with grandchildren",
    "Chinese New Year",
    "old faded 1970s photograph",
    "legal document",
    "three generations together",
]


# --- Metrics ---


def precision_at_k(relevant: list[bool], k: int) -> float:
    """Precision@k: fraction of top-k results that are relevant."""
    return sum(relevant[:k]) / k if k > 0 else 0.0


def ndcg_at_k(relevant: list[bool], k: int) -> float:
    """Normalized discounted cumulative gain at k."""
    dcg = sum(
        (1.0 if rel else 0.0) / math.log2(i + 2)
        for i, rel in enumerate(relevant[:k])
    )
    ideal = sorted(relevant[:k], reverse=True)
    idcg = sum(
        (1.0 if rel else 0.0) / math.log2(i + 2)
        for i, rel in enumerate(ideal)
    )
    return dcg / idcg if idcg > 0 else 0.0


# --- Evaluation runners ---


def run_text_to_image_queries(
    db_path: Path,
    vec_table: str = "vec_images",
    k: int = 10,
) -> list[dict]:
    """Embed text queries and search against image embeddings.
    Returns results for human relevance judgment."""
    client = embed.get_client()
    conn = vecdb.connect(db_path)
    results = []

    for query_text in TEXT_QUERIES:
        t0 = time.monotonic()
        qr = embed.embed_query(client, query_text,
                               dimensions=_dims_for_table(vec_table))
        query_ms = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        hits = vecdb.knn_search_with_metadata(conn, vec_table, qr["vector"],
                                              k=k)
        search_ms = (time.monotonic() - t0) * 1000

        results.append({
            "query": query_text,
            "query_latency_ms": query_ms,
            "search_latency_ms": search_ms,
            "results": hits,
            "relevance": [None] * len(hits),  # to be filled by human
        })

    conn.close()
    return results


def run_image_to_image(
    db_path: Path,
    query_sha256s: list[str],
    vec_table: str = "vec_images",
    k: int = 6,
) -> list[dict]:
    """Find nearest neighbor images for given image SHA256s."""
    conn = vecdb.connect(db_path)
    results = []

    for sha in query_sha256s:
        # Get the query image's own vector
        rows = list(conn.execute(
            f"SELECT embedding FROM {vec_table} WHERE sha256 = ?", (sha,)
        ))
        if not rows:
            results.append({"query_sha256": sha, "error": "not found"})
            continue

        import numpy as np
        vec = np.frombuffer(rows[0][0], dtype=np.float32).tolist()

        t0 = time.monotonic()
        # k+1 because the query itself will be the top result
        hits = vecdb.knn_search_with_metadata(conn, vec_table, vec, k=k + 1)
        search_ms = (time.monotonic() - t0) * 1000

        # Remove self-match
        hits = [h for h in hits if h["sha256"] != sha][:k]

        results.append({
            "query_sha256": sha,
            "search_latency_ms": search_ms,
            "results": hits,
            "coherence": None,  # human judgment
        })

    conn.close()
    return results


def run_cross_modal(
    db_path: Path,
    doc_sha256s: list[str],
    photo_sha256s: list[str],
) -> dict:
    """Cross-modal retrieval: doc text → image search, photo → doc text search."""
    conn = vecdb.connect(db_path)
    results = {"doc_to_image": [], "image_to_doc": []}

    # Document text embeddings → search vec_images
    for sha in doc_sha256s:
        rows = list(conn.execute(
            "SELECT embedding FROM vec_documents WHERE sha256 = ?", (sha,)
        ))
        if not rows:
            continue
        import numpy as np
        vec = np.frombuffer(rows[0][0], dtype=np.float32).tolist()
        hits = vecdb.knn_search_with_metadata(conn, "vec_images", vec, k=5)
        meta_rows = list(conn.execute(
            "SELECT source_path FROM embedded_assets WHERE sha256 = ?", (sha,)
        ))
        results["doc_to_image"].append({
            "query_sha256": sha,
            "query_source": meta_rows[0][0] if meta_rows else None,
            "results": hits,
            "relevance": [None] * len(hits),
        })

    # Photo image embeddings → search vec_text (document summaries)
    for sha in photo_sha256s:
        rows = list(conn.execute(
            "SELECT embedding FROM vec_images WHERE sha256 = ?", (sha,)
        ))
        if not rows:
            continue
        import numpy as np
        vec = np.frombuffer(rows[0][0], dtype=np.float32).tolist()
        hits = vecdb.knn_search_with_metadata(conn, "vec_text", vec, k=5)
        meta_rows = list(conn.execute(
            "SELECT source_path FROM embedded_assets WHERE sha256 = ?", (sha,)
        ))
        results["image_to_doc"].append({
            "query_sha256": sha,
            "query_source": meta_rows[0][0] if meta_rows else None,
            "results": hits,
            "relevance": [None] * len(hits),
        })

    conn.close()
    return results


def compute_metrics(query_results: list[dict]) -> dict:
    """Compute aggregate metrics from judged query results."""
    p5_scores, p10_scores, ndcg_scores = [], [], []

    for qr in query_results:
        rel = qr.get("relevance", [])
        # Skip unjudged queries
        if not rel or all(r is None for r in rel):
            continue
        rel_bool = [bool(r) for r in rel]
        p5_scores.append(precision_at_k(rel_bool, 5))
        p10_scores.append(precision_at_k(rel_bool, 10))
        ndcg_scores.append(ndcg_at_k(rel_bool, 10))

    n = len(p5_scores)
    return {
        "queries_judged": n,
        "precision_at_5": sum(p5_scores) / n if n else None,
        "precision_at_10": sum(p10_scores) / n if n else None,
        "ndcg_at_10": sum(ndcg_scores) / n if n else None,
        "per_query_p5": p5_scores,
    }


def _dims_for_table(table: str) -> int:
    """Infer dimensionality from table name."""
    if "768" in table:
        return 768
    if "1536" in table:
        return 1536
    return config.FULL_DIMENSIONS


# --- CLI ---


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "phase2":
        if not config.EMBEDDINGS_DB.exists():
            print("ERROR: embeddings.db not found. Run Phase 1 first.")
            sys.exit(1)

        out_dir = config.RUNS_DIR / "p2-retrieval"
        out_dir.mkdir(parents=True, exist_ok=True)

        # 2a — Text-to-image
        print("Running text-to-image queries...")
        t2i = run_text_to_image_queries(config.EMBEDDINGS_DB)
        (out_dir / "text-to-image-results.json").write_text(
            json.dumps(t2i, indent=2))
        print(f"  {len(t2i)} queries, results saved")

        # 2b — Image-to-image (pick first 5 photos from locked inputs)
        locked = json.loads(
            (config.RUNS_DIR / "p0-setup" / "locked-inputs.json").read_text()
        )
        photo_shas = [a["sha256"] for a in locked["assets"]
                      if a["content_type"] == "photo"][:5]
        print("Running image-to-image queries...")
        i2i = run_image_to_image(config.EMBEDDINGS_DB, photo_shas)
        (out_dir / "image-to-image-results.json").write_text(
            json.dumps(i2i, indent=2))
        print(f"  {len(i2i)} queries, results saved")

        # 2c — Cross-modal
        doc_shas = [a["sha256"] for a in locked["assets"]
                    if a["content_type"] == "document"][:3]
        print("Running cross-modal queries...")
        xm = run_cross_modal(config.EMBEDDINGS_DB, doc_shas, photo_shas[:3])
        (out_dir / "cross-modal-results.json").write_text(
            json.dumps(xm, indent=2))
        print(f"  doc→image: {len(xm['doc_to_image'])}, "
              f"image→doc: {len(xm['image_to_doc'])}")

        print(f"\nResults saved to {out_dir}/")
        print("Next: Review results and add relevance judgments, "
              "then run 'metrics' command.")

    elif cmd == "metrics":
        out_dir = config.RUNS_DIR / "p2-retrieval"
        t2i_path = out_dir / "text-to-image-results.json"
        if not t2i_path.exists():
            print("ERROR: Run phase2 first.")
            sys.exit(1)

        t2i = json.loads(t2i_path.read_text())
        metrics = compute_metrics(t2i)
        print(json.dumps(metrics, indent=2))
        (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    elif cmd == "phase3-eval":
        # Compare retrieval at different dimensions
        out_dir = config.RUNS_DIR / "p3-dimensions"
        out_dir.mkdir(parents=True, exist_ok=True)
        comparison = {}

        for table, label in [
            ("vec_images", "3072"),
            ("vec_images_768", "768"),
            ("vec_images_1536", "1536"),
        ]:
            print(f"Evaluating {label}d...")
            try:
                results = run_text_to_image_queries(
                    config.EMBEDDINGS_DB, vec_table=table)
                (out_dir / f"text-to-image-{label}d.json").write_text(
                    json.dumps(results, indent=2))
                comparison[label] = {
                    "queries": len(results),
                    "avg_search_latency_ms": (
                        sum(r["search_latency_ms"] for r in results)
                        / len(results)
                    ),
                }
            except Exception as e:
                comparison[label] = {"error": str(e)}

        (out_dir / "dimension-comparison.json").write_text(
            json.dumps(comparison, indent=2))
        print(json.dumps(comparison, indent=2))

    else:
        print("Usage: python -m ...evaluate [phase2|metrics|phase3-eval]")
        sys.exit(1)
