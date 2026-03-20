"""Semantic search CLI for the embedding database.

Usage:
    python experiments/0003-multimodal-embeddings/search.py "wedding ceremony"
    python experiments/0003-multimodal-embeddings/search.py "grandmother" --k 10
    python experiments/0003-multimodal-embeddings/search.py --similar SHA256_PREFIX
    python experiments/0003-multimodal-embeddings/search.py --similar path/to/photo.jpg
"""

import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from experiments import __init__  # noqa: F401

# Use importlib for hyphenated package name
import importlib
config = importlib.import_module("experiments.0003-multimodal-embeddings.src.config")
vecdb = importlib.import_module("experiments.0003-multimodal-embeddings.src.vecdb")
embed = importlib.import_module("experiments.0003-multimodal-embeddings.src.embed")


def load_description(manifest_path: str | None) -> str:
    """Get description from manifest."""
    if not manifest_path:
        return ""
    p = Path(manifest_path)
    if not p.exists():
        return ""
    m = json.loads(p.read_text())
    a = m.get("analysis", {})
    return a.get("description_en", a.get("summary_en", ""))


def text_search(query: str, k: int = 5, table: str = "vec_images"):
    """Search photos by text query."""
    client = embed.get_client()
    conn = vecdb.connect(config.EMBEDDINGS_DB)

    t0 = time.monotonic()
    qr = embed.embed_query(client, query)
    embed_ms = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    hits = vecdb.knn_search_with_metadata(conn, table, qr["vector"], k=k)
    search_ms = (time.monotonic() - t0) * 1000

    print(f'Query: "{query}"')
    print(f"Embed: {embed_ms:.0f}ms | Search: {search_ms:.0f}ms | "
          f"{len(hits)} results\n")

    for i, h in enumerate(hits):
        desc = load_description(h.get("manifest_path"))
        source = Path(h.get("source_path", "")).name
        print(f"  {i+1}. [{h['distance']:.4f}] {source}")
        if desc:
            print(f"     {desc[:100]}")
        print()

    conn.close()


def similar_search(identifier: str, k: int = 5):
    """Find similar photos by SHA256 prefix or file path."""
    conn = vecdb.connect(config.EMBEDDINGS_DB)

    # Check if it's a file path
    if Path(identifier).suffix:
        # Embed the image directly
        client = embed.get_client()
        src = Path(identifier)
        if not src.exists():
            print(f"File not found: {identifier}")
            return

        t0 = time.monotonic()
        result = embed.embed_image(client, src)
        embed_ms = (time.monotonic() - t0) * 1000
        query_vec = result["vector"]
        print(f"Query: {src.name} (embed: {embed_ms:.0f}ms)\n")
    else:
        # Look up by SHA256 prefix
        rows = list(conn.execute(
            "SELECT sha256, embedding FROM vec_images WHERE sha256 LIKE ?",
            (f"{identifier}%",),
        ))
        if not rows:
            print(f"No embedding found for SHA256 prefix: {identifier}")
            return

        import numpy as np
        sha = rows[0][0]
        query_vec = np.frombuffer(rows[0][1], dtype=np.float32).tolist()

        meta = list(conn.execute(
            "SELECT source_path FROM embedded_assets WHERE sha256 = ?",
            (sha,),
        ))
        source = Path(meta[0][0]).name if meta else sha[:12]
        desc = ""
        meta2 = list(conn.execute(
            "SELECT manifest_path FROM embedded_assets WHERE sha256 = ?",
            (sha,),
        ))
        if meta2:
            desc = load_description(meta2[0][0])
        print(f"Query: {source}")
        if desc:
            print(f"  {desc[:100]}")
        print()

    t0 = time.monotonic()
    hits = vecdb.knn_search_with_metadata(
        conn, "vec_images", query_vec, k=k + 1
    )
    search_ms = (time.monotonic() - t0) * 1000

    # Remove self-match if searching by SHA
    if not Path(identifier).suffix:
        hits = [h for h in hits if not h["sha256"].startswith(identifier)]
    hits = hits[:k]

    print(f"Search: {search_ms:.0f}ms | {len(hits)} similar photos\n")

    for i, h in enumerate(hits):
        desc = load_description(h.get("manifest_path"))
        source = Path(h.get("source_path", "")).name
        print(f"  {i+1}. [{h['distance']:.4f}] {source}")
        if desc:
            print(f"     {desc[:100]}")
        print()

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Semantic photo search")
    parser.add_argument("query", nargs="?", help="Text search query")
    parser.add_argument("--similar", "-s", help="Find similar by SHA256 prefix or image path")
    parser.add_argument("--k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--docs", action="store_true", help="Search documents instead of photos")
    args = parser.parse_args()

    if args.similar:
        similar_search(args.similar, k=args.k)
    elif args.query:
        table = "vec_documents" if args.docs else "vec_images"
        text_search(args.query, k=args.k, table=table)
    else:
        parser.print_help()
