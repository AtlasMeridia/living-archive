"""Experiment 0003 configuration — paths, env vars, model defaults."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- API ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
EMBEDDING_MODEL = "gemini-embedding-2-preview"
FULL_DIMENSIONS = 3072

# --- Paths ---
EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EXPERIMENT_ROOT.parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "data")))
CATALOG_DB = DATA_DIR / "catalog.db"
SYNTHESIS_DB = DATA_DIR / "synthesis.db"
EMBEDDINGS_DB = EXPERIMENT_ROOT / "embeddings.db"
RUNS_DIR = EXPERIMENT_ROOT / "runs"

# --- NAS (read-only source files) ---
FAMILY_ROOT = Path(os.environ.get(
    "FAMILY_ROOT", "/Volumes/MNEME/05_PROJECTS/Living Archive/Family"
))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(FAMILY_ROOT / "Media")))
DOCUMENTS_ROOT = Path(os.environ.get(
    "DOCUMENTS_ROOT", str(FAMILY_ROOT / "Documents")
))

# --- Image prep ---
MAX_EDGE = 2048
JPEG_QUALITY = 85
