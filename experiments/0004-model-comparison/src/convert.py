"""TIFF/JPEG to analysis-ready JPEG conversion."""

from pathlib import Path

from PIL import Image

from . import config


def prepare_for_analysis(src: Path, dst: Path) -> None:
    """Convert a photo to JPEG, resizing so longest edge <= MAX_EDGE."""
    with Image.open(src) as img:
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > config.MAX_EDGE:
            scale = config.MAX_EDGE / max(w, h)
            img = img.resize(
                (int(w * scale), int(h * scale)), Image.Resampling.LANCZOS
            )
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "JPEG", quality=config.JPEG_QUALITY)


def needs_conversion(path: Path) -> bool:
    """True if the file needs conversion/resizing for analysis."""
    if path.suffix.lower() in (".tif", ".tiff"):
        return True
    with Image.open(path) as img:
        return max(img.size) > config.MAX_EDGE
