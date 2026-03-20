"""Gemini Embedding 2 API client — embed images, text, and PDFs."""

import io
import json
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from . import config, vecdb


def get_client() -> genai.Client:
    """Create Gemini API client."""
    if not config.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY not set")
    return genai.Client(api_key=config.GOOGLE_API_KEY)


# --- Image preparation (local reimplementation, no src/ imports) ---


def prepare_image(src: Path) -> bytes:
    """Convert image to JPEG bytes, resizing if needed. Handles TIFF."""
    with Image.open(src) as img:
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > config.MAX_EDGE:
            scale = config.MAX_EDGE / max(w, h)
            img = img.resize(
                (int(w * scale), int(h * scale)), Image.Resampling.LANCZOS
            )
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=config.JPEG_QUALITY)
        return buf.getvalue()


# --- Embedding functions ---


def embed_image(
    client: genai.Client,
    image_path: Path,
    dimensions: int = config.FULL_DIMENSIONS,
) -> dict:
    """Embed an image file. Returns {vector, latency_ms, input_tokens}."""
    jpeg_bytes = prepare_image(image_path)

    t0 = time.monotonic()
    result = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=types.Content(
            parts=[types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")]
        ),
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=dimensions,
        ),
    )
    latency_ms = (time.monotonic() - t0) * 1000

    vec = result.embeddings[0].values
    return {
        "vector": vec,
        "latency_ms": latency_ms,
        "input_tokens": getattr(result, "input_tokens", None),
    }


def embed_text(
    client: genai.Client,
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
    dimensions: int = config.FULL_DIMENSIONS,
) -> dict:
    """Embed a text string. Returns {vector, latency_ms, input_tokens}."""
    t0 = time.monotonic()
    result = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=dimensions,
        ),
    )
    latency_ms = (time.monotonic() - t0) * 1000

    vec = result.embeddings[0].values
    return {
        "vector": vec,
        "latency_ms": latency_ms,
        "input_tokens": getattr(result, "input_tokens", None),
    }


def embed_query(
    client: genai.Client,
    query: str,
    dimensions: int = config.FULL_DIMENSIONS,
) -> dict:
    """Embed a search query (uses RETRIEVAL_QUERY task type)."""
    return embed_text(client, query, task_type="RETRIEVAL_QUERY",
                      dimensions=dimensions)


def embed_pdf(
    client: genai.Client,
    pdf_path: Path,
    dimensions: int = config.FULL_DIMENSIONS,
) -> dict:
    """Embed a PDF file directly. Returns {vector, latency_ms, input_tokens}."""
    pdf_bytes = pdf_path.read_bytes()

    t0 = time.monotonic()
    result = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=types.Content(
            parts=[types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")]
        ),
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=dimensions,
        ),
    )
    latency_ms = (time.monotonic() - t0) * 1000

    vec = result.embeddings[0].values
    return {
        "vector": vec,
        "latency_ms": latency_ms,
        "input_tokens": getattr(result, "input_tokens", None),
    }


# --- Batch embedding (Phase 1) ---


def load_manifest(path: str) -> dict | None:
    """Load a manifest JSON file."""
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def get_text_for_asset(manifest: dict, content_type: str) -> str | None:
    """Extract embeddable text from a manifest."""
    analysis = manifest.get("analysis", {})
    if content_type == "photo":
        return analysis.get("description_en")
    elif content_type == "document":
        return analysis.get("summary_en")
    return None


def embed_test_set(
    locked_inputs_path: Path,
    db_path: Path,
    dimensions: int = config.FULL_DIMENSIONS,
) -> dict:
    """Embed all assets in the locked test set. Returns stats dict."""
    inputs = json.loads(locked_inputs_path.read_text())
    client = get_client()
    conn = vecdb.init_db(db_path)

    stats = {"total": 0, "succeeded": 0, "failed": 0, "assets": []}

    for asset in inputs["assets"]:
        sha = asset["sha256"]
        content_type = asset["content_type"]
        source_path = asset["source_path"]
        manifest_path = asset.get("manifest_path")
        stats["total"] += 1

        asset_stat = {"sha256": sha, "content_type": content_type, "errors": []}

        # 1. Image embedding (photos only)
        if content_type == "photo":
            src = Path(source_path)
            if src.exists():
                try:
                    vec_table = f"vec_images{'_' + str(dimensions) if dimensions != config.FULL_DIMENSIONS else ''}"
                    if dimensions == config.FULL_DIMENSIONS:
                        vec_table = "vec_images"
                    result = embed_image(client, src, dimensions=dimensions)
                    vecdb.insert_embedding(
                        conn, sha256=sha, content_type=content_type,
                        source_path=str(source_path), manifest_path=manifest_path,
                        embedding_input="image", vector=result["vector"],
                        table=vec_table, latency_ms=result["latency_ms"],
                        input_tokens=result.get("input_tokens"),
                    )
                    asset_stat["image_latency_ms"] = result["latency_ms"]
                except Exception as e:
                    asset_stat["errors"].append(f"image: {e}")
            else:
                asset_stat["errors"].append(f"image: file not found: {source_path}")

        # 2. Text embedding (from manifest description/summary)
        if manifest_path:
            manifest = load_manifest(manifest_path)
            if manifest:
                text = get_text_for_asset(manifest, content_type)
                if text:
                    try:
                        result = embed_text(client, text, dimensions=dimensions)
                        table = "vec_text" if content_type == "photo" else "vec_documents"
                        vecdb.insert_embedding(
                            conn, sha256=sha, content_type=content_type,
                            source_path=str(source_path),
                            manifest_path=manifest_path,
                            embedding_input="text", vector=result["vector"],
                            table=table, latency_ms=result["latency_ms"],
                            input_tokens=result.get("input_tokens"),
                        )
                        asset_stat["text_latency_ms"] = result["latency_ms"]
                    except Exception as e:
                        asset_stat["errors"].append(f"text: {e}")

        # 3. PDF embedding (documents only)
        if content_type == "document":
            src = Path(source_path)
            if src.exists() and src.suffix.lower() == ".pdf":
                try:
                    result = embed_pdf(client, src, dimensions=dimensions)
                    vecdb.insert_embedding(
                        conn, sha256=sha, content_type=content_type,
                        source_path=str(source_path),
                        manifest_path=manifest_path,
                        embedding_input="pdf", vector=result["vector"],
                        table="vec_documents", latency_ms=result["latency_ms"],
                        input_tokens=result.get("input_tokens"),
                    )
                    asset_stat["pdf_latency_ms"] = result["latency_ms"]
                except Exception as e:
                    asset_stat["errors"].append(f"pdf: {e}")

        if asset_stat["errors"]:
            stats["failed"] += 1
        else:
            stats["succeeded"] += 1
        stats["assets"].append(asset_stat)

    conn.close()
    return stats


# --- CLI ---


def validate_api() -> dict:
    """Validate API access with a test text and test image embedding."""
    client = get_client()
    results = {}

    # Test text embedding
    text_result = embed_text(client, "A family photograph from the 1970s")
    results["text"] = {
        "dimensions": len(text_result["vector"]),
        "latency_ms": text_result["latency_ms"],
        "sample_values": text_result["vector"][:5],
    }

    # Test image embedding (1x1 white JPEG)
    img = Image.new("RGB", (64, 64), "white")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    jpeg_bytes = buf.getvalue()

    t0 = time.monotonic()
    result = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=types.Content(
            parts=[types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")]
        ),
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=config.FULL_DIMENSIONS,
        ),
    )
    latency_ms = (time.monotonic() - t0) * 1000
    vec = result.embeddings[0].values

    results["image"] = {
        "dimensions": len(vec),
        "latency_ms": latency_ms,
        "sample_values": vec[:5],
    }

    return results


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "validate"

    if cmd == "validate":
        results = validate_api()
        print(json.dumps(results, indent=2))

    elif cmd == "phase1":
        locked = config.RUNS_DIR / "p0-setup" / "locked-inputs.json"
        if not locked.exists():
            print(f"ERROR: {locked} not found. Run Phase 0 first.")
            sys.exit(1)
        stats = embed_test_set(locked, config.EMBEDDINGS_DB)
        out_dir = config.RUNS_DIR / "p1-embed"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "embed-stats.json").write_text(json.dumps(stats, indent=2))
        print(f"Embedded {stats['succeeded']}/{stats['total']} assets "
              f"({stats['failed']} failed)")

    elif cmd == "phase3":
        locked = config.RUNS_DIR / "p0-setup" / "locked-inputs.json"
        if not locked.exists():
            print(f"ERROR: {locked} not found.")
            sys.exit(1)
        for dims in (768, 1536):
            print(f"\nEmbedding at {dims} dimensions...")
            stats = embed_test_set(locked, config.EMBEDDINGS_DB,
                                   dimensions=dims)
            out_dir = config.RUNS_DIR / "p3-dimensions"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"embed-stats-{dims}.json").write_text(
                json.dumps(stats, indent=2))
            print(f"  {dims}d: {stats['succeeded']}/{stats['total']} "
                  f"({stats['failed']} failed)")

    elif cmd == "corpus":
        import sqlite3 as stdlib_sqlite3

        dims_list = [config.FULL_DIMENSIONS, 768]
        catalog = stdlib_sqlite3.connect(str(config.CATALOG_DB))
        catalog.row_factory = stdlib_sqlite3.Row

        rows = catalog.execute(
            """SELECT sha256, path, content_type, manifest_path
               FROM assets
               WHERE status = 'indexed'
                 AND manifest_path IS NOT NULL
               ORDER BY content_type, path"""
        ).fetchall()
        catalog.close()

        conn = vecdb.init_db(config.EMBEDDINGS_DB)

        # Find already-embedded sha256s to support resumption
        already = set()
        for r in conn.execute(
            "SELECT sha256 FROM embedded_assets"
        ):
            already.add(r[0])

        # Resolve paths
        assets = []
        for r in rows:
            ct = r["content_type"]
            source = r["path"]
            mp = r["manifest_path"]
            if not Path(source).is_absolute():
                if ct == "photo":
                    source = str(config.MEDIA_ROOT / source)
                else:
                    source = str(config.DOCUMENTS_ROOT / source)
            if mp and not Path(mp).is_absolute():
                if ct == "photo":
                    mp = str(config.DATA_DIR / "photos" / mp)
                else:
                    mp = str(config.DATA_DIR / "documents" / mp)
            assets.append({
                "sha256": r["sha256"], "content_type": ct,
                "source_path": source, "manifest_path": mp,
            })

        to_embed = [a for a in assets if a["sha256"] not in already]
        print(f"Corpus: {len(assets)} total, {len(already)} already done, "
              f"{len(to_embed)} remaining")

        client = get_client()
        succeeded = 0
        failed = 0
        t_start = time.monotonic()

        for i, asset in enumerate(to_embed):
            sha = asset["sha256"]
            ct = asset["content_type"]
            src_path = asset["source_path"]
            mp = asset["manifest_path"]

            errors = []

            # Image embedding (photos) at both dimensions
            if ct == "photo":
                src = Path(src_path)
                if src.exists():
                    for dims in dims_list:
                        table = "vec_images" if dims == config.FULL_DIMENSIONS else f"vec_images_{dims}"
                        try:
                            result = embed_image(client, src, dimensions=dims)
                            vecdb.insert_embedding(
                                conn, sha256=sha, content_type=ct,
                                source_path=src_path, manifest_path=mp,
                                embedding_input="image", vector=result["vector"],
                                table=table, latency_ms=result["latency_ms"],
                                input_tokens=result.get("input_tokens"),
                            )
                        except Exception as e:
                            errors.append(f"image-{dims}: {e}")
                else:
                    errors.append(f"file not found: {src_path}")

            # Text embedding from manifest
            if mp:
                manifest = load_manifest(mp)
                if manifest:
                    text = get_text_for_asset(manifest, ct)
                    if text:
                        table = "vec_text" if ct == "photo" else "vec_documents"
                        try:
                            result = embed_text(client, text)
                            vecdb.insert_embedding(
                                conn, sha256=sha, content_type=ct,
                                source_path=src_path, manifest_path=mp,
                                embedding_input="text", vector=result["vector"],
                                table=table, latency_ms=result["latency_ms"],
                                input_tokens=result.get("input_tokens"),
                            )
                        except Exception as e:
                            errors.append(f"text: {e}")

            if errors:
                failed += 1
                print(f"  [{i+1}/{len(to_embed)}] FAIL {sha[:12]} "
                      f"— {errors[0][:80]}")
            else:
                succeeded += 1

            if (i + 1) % 50 == 0 or i == len(to_embed) - 1:
                elapsed = time.monotonic() - t_start
                rate = (i + 1) / elapsed * 3600 if elapsed > 0 else 0
                print(f"  [{i+1}/{len(to_embed)}] {succeeded} ok, "
                      f"{failed} fail | {elapsed:.0f}s | {rate:.0f}/hr")

        conn.close()
        print(f"\nDone: {succeeded} succeeded, {failed} failed")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python -m ...embed "
              "[validate|phase1|phase3|corpus]")
        sys.exit(1)
