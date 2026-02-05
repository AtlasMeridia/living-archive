"""TIFF to JPEG conversion and SHA-256 hashing."""

import hashlib
from pathlib import Path

from PIL import Image

MAX_EDGE = 2048
JPEG_QUALITY = 85


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tiff_to_jpeg(src: Path, dst: Path) -> None:
    """Convert a TIFF to JPEG, resizing so the longest edge <= MAX_EDGE."""
    with Image.open(src) as img:
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_EDGE:
            scale = MAX_EDGE / max(w, h)
            img = img.resize(
                (int(w * scale), int(h * scale)), Image.Resampling.LANCZOS
            )
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "JPEG", quality=JPEG_QUALITY)


def find_tiffs(directory: Path) -> list[Path]:
    """Find all TIFF files in a directory (non-recursive)."""
    tiffs = []
    for ext in ("*.tiff", "*.tif", "*.TIFF", "*.TIF"):
        tiffs.extend(directory.glob(ext))
    return sorted(tiffs)
