"""Photo preparation (TIFF/JPEG → analysis-ready JPEG) and SHA-256 hashing."""

import hashlib
from pathlib import Path

from PIL import Image

MAX_EDGE = 2048
JPEG_QUALITY = 85
MAX_ANALYSIS_BYTES = 5 * 1024 * 1024


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare_for_analysis(src: Path, dst: Path) -> None:
    """Convert a photo to JPEG, resizing so the longest edge <= MAX_EDGE."""
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


def find_photos(directory: Path) -> list[Path]:
    """Find all TIFF and JPEG files in a directory (non-recursive)."""
    photos = []
    for ext in ("*.tiff", "*.tif", "*.TIFF", "*.TIF",
                "*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
        photos.extend(directory.glob(ext))
    return sorted(photos)


def needs_conversion(path: Path) -> bool:
    """Return True if the file needs conversion/resizing for analysis.

    TIFFs always need conversion. Files mislabeled as JPEG but containing TIFF
    bytes also need conversion. Real JPEGs need normalization if they exceed
    the analysis edge/size limits.
    """
    if path.suffix.lower() in (".tif", ".tiff"):
        return True
    with Image.open(path) as img:
        if (img.format or "").upper() != "JPEG":
            return True
        return max(img.size) > MAX_EDGE or path.stat().st_size > MAX_ANALYSIS_BYTES
