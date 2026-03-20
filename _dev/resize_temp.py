#!/usr/bin/env python3
"""Temporary script to resize photos for analysis."""
from PIL import Image

src = "/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Media/2025-2026 Digital Revolution Scans/1st Round/Jpeg/Albumpage/Photo_028.jpeg"
dst = "/tmp/photo_028_thumb.jpeg"

img = Image.open(src)
print(f"Original size: {img.size}, mode: {img.mode}")
img.thumbnail((1200, 1200), Image.LANCZOS)
print(f"Thumbnail size: {img.size}")
img.save(dst, "JPEG", quality=80)
print(f"Saved to {dst}")
