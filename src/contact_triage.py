"""Contact sheet triage for bulk FastFoto scans.

Tiles photos into numbered grids, sends each grid to Haiku for quick
dedup/quality filtering before running full analysis on 7,600+ scans.
Saves results to data/triage/<album>_triage.json.

Usage:
    python -m src.contact_triage <album_dir>
    python -m src.contact_triage <album_dir> --grid-size 16 --dry-run
"""

import argparse
import base64
import io
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config
from .convert import find_photos

log = logging.getLogger("living_archive")

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Contact sheet geometry
CELL_W = 300   # pixels per thumbnail cell
CELL_H = 250
LABEL_H = 22   # label strip height below each cell
COLS = 4       # columns per sheet

TRIAGE_PROMPT = """You are triaging a contact sheet of family archive photos from a bulk flatbed scanner (Epson FastFoto).

The image shows a grid of photos. Each photo has a number label below it. Your job is quick pre-filtering before expensive AI analysis.

Flag for SKIP only:
- **Near-duplicates**: Same scene scanned twice or nearly identical shots (very common in bulk scanning)
- **Completely blank**: No photographic content (pure white, pure black, or featureless gray)
- **Pure scanner artifacts**: Solid scan noise with no photo content

KEEP everything else — including faded, aged, torn, water-damaged, or low-quality photos. Archival value matters more than quality.

Respond ONLY with valid JSON, no surrounding text or code fences:
{
  "photos": {
    "1": {"action": "keep"},
    "2": {"action": "skip", "reason": "near-duplicate of photo 3"},
    "3": {"action": "keep"}
  },
  "notes": "optional overall observation"
}

Be very conservative — when in doubt, KEEP. Only flag clear duplicates and blank sheets."""


def _load_font(size: int = 15) -> ImageFont.ImageFont:
    """Load a readable font, falling back to PIL default."""
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def build_contact_sheet(photos: list[Path], start_idx: int) -> bytes:
    """Tile photos into a numbered contact sheet. Returns JPEG bytes."""
    n = len(photos)
    rows = (n + COLS - 1) // COLS
    sheet_w = COLS * CELL_W
    sheet_h = rows * (CELL_H + LABEL_H)

    sheet = Image.new("RGB", (sheet_w, sheet_h), (35, 35, 35))
    draw = ImageDraw.Draw(sheet)
    font = _load_font()

    for i, photo_path in enumerate(photos):
        col = i % COLS
        row = i // COLS
        cell_x = col * CELL_W
        cell_y = row * (CELL_H + LABEL_H)
        label_num = start_idx + i + 1  # 1-indexed, matches prompt labels

        # Thumbnail into cell
        try:
            with Image.open(photo_path) as img:
                img = img.convert("RGB")
                img.thumbnail((CELL_W, CELL_H), Image.Resampling.LANCZOS)
                x_off = cell_x + (CELL_W - img.width) // 2
                y_off = cell_y + (CELL_H - img.height) // 2
                sheet.paste(img, (x_off, y_off))
        except Exception as exc:
            log.debug("  Could not open %s: %s", photo_path.name, exc)
            draw.rectangle(
                [cell_x, cell_y, cell_x + CELL_W, cell_y + CELL_H],
                fill=(70, 20, 20),
            )

        # Numbered label strip
        label_y = cell_y + CELL_H
        draw.rectangle(
            [cell_x, label_y, cell_x + CELL_W, label_y + LABEL_H],
            fill=(15, 15, 15),
        )
        draw.text((cell_x + 6, label_y + 3), str(label_num),
                  fill=(210, 210, 210), font=font)

    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=78)
    return buf.getvalue()


def _call_haiku(sheet_bytes: bytes, client) -> dict:
    """Send contact sheet to Haiku, return parsed triage dict."""
    b64 = base64.standard_b64encode(sheet_bytes).decode()

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                },
                {"type": "text", "text": TRIAGE_PROMPT},
            ],
        }],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[:-3].rstrip()

    result = json.loads(raw)
    result["_usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return result


def run_triage(album_dir: Path, grid_size: int = 16, dry_run: bool = False) -> dict:
    """Triage an album via contact sheet grids. Returns summary dict."""
    photos = find_photos(album_dir)
    if not photos:
        log.error("No photos found in %s", album_dir)
        return {}

    n_grids = (len(photos) + grid_size - 1) // grid_size
    log.info("Contact sheet triage: %s", album_dir.name)
    log.info("  %d photos → %d grids of up to %d", len(photos), n_grids, grid_size)

    if dry_run:
        log.info("  Dry run — no API calls")
        return {"dry_run": True, "total_photos": len(photos), "grids": n_grids}

    if not config.ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY not set — Haiku triage requires direct API access")
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    keep: list[str] = []
    skip: list[str] = []
    skip_reasons: dict[str, str] = {}
    total_in = 0
    total_out = 0

    batches = [photos[i:i + grid_size] for i in range(0, len(photos), grid_size)]

    for batch_idx, batch in enumerate(batches):
        start_idx = batch_idx * grid_size
        log.info("  Grid %d/%d (photos %d–%d)",
                 batch_idx + 1, len(batches), start_idx + 1, start_idx + len(batch))

        sheet_bytes = build_contact_sheet(batch, start_idx)
        result = _call_haiku(sheet_bytes, client)

        total_in += result["_usage"]["input_tokens"]
        total_out += result["_usage"]["output_tokens"]

        photos_triage = result.get("photos", {})
        for i, photo_path in enumerate(batch):
            label = str(start_idx + i + 1)
            info = photos_triage.get(label, {})
            action = info.get("action", "keep").lower()
            if action == "skip":
                reason = info.get("reason", "")
                skip.append(photo_path.name)
                if reason:
                    skip_reasons[photo_path.name] = reason
                log.info("    SKIP [%s] %s", label, reason or "flagged")

        kept_in_batch = len(batch) - sum(
            1 for i in range(len(batch))
            if photos_triage.get(str(start_idx + i + 1), {}).get("action", "keep") == "skip"
        )
        log.info("    → %d keep, %d skip (tokens: %d in / %d out)",
                 kept_in_batch,
                 len(batch) - kept_in_batch,
                 result["_usage"]["input_tokens"],
                 result["_usage"]["output_tokens"])

    # Build keep list from photos not in skip
    skip_set = set(skip)
    keep = [p.name for p in photos if p.name not in skip_set]

    # Resolve album label
    try:
        album_label = str(album_dir.relative_to(config.MEDIA_ROOT))
    except ValueError:
        album_label = album_dir.name

    summary = {
        "album": album_label,
        "triage_date": datetime.now(timezone.utc).isoformat(),
        "total_photos": len(photos),
        "grids_processed": len(batches),
        "grid_size": grid_size,
        "keep_count": len(keep),
        "skip_count": len(skip),
        "keep": keep,
        "skip": skip,
        "skip_reasons": skip_reasons,
        "tokens": {"input": total_in, "output": total_out},
        "model": HAIKU_MODEL,
    }

    # Persist results
    triage_dir = config.DATA_DIR / "triage"
    triage_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w-]", "_", album_dir.name)
    out_path = triage_dir / f"{slug}_triage.json"
    out_path.write_text(json.dumps(summary, indent=2))

    log.info("")
    log.info("Done: %d keep, %d skip (%.1f%% deduped/blanked)",
             len(keep), len(skip), 100 * len(skip) / len(photos) if photos else 0)
    log.info("Tokens: %d in / %d out", total_in, total_out)
    log.info("Saved: %s", out_path)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Contact sheet triage for FastFoto scans via Haiku"
    )
    parser.add_argument("album_dir", help="Album directory to triage")
    parser.add_argument("--grid-size", type=int, default=16,
                        help="Photos per contact sheet grid (default: 16, max: 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview grid plan without calling API")
    args = parser.parse_args()

    config.setup_logging()

    grid_size = min(max(args.grid_size, 4), 20)
    album_dir = Path(args.album_dir).resolve()

    if not album_dir.is_dir():
        log.error("Not a directory: %s", album_dir)
        sys.exit(1)

    run_triage(album_dir, grid_size=grid_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
