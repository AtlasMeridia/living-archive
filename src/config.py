"""Path constants and environment variable loading."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- API keys ---
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
IMMICH_API_KEY = os.environ["IMMICH_API_KEY"]
IMMICH_URL = os.environ.get("IMMICH_URL", "http://mneme.local:2283")

# --- Paths ---
MEDIA_ROOT = Path(os.environ.get(
    "MEDIA_ROOT", "/Volumes/MNEME/05_PROJECTS/Living Archive/Media"
))
SLICE_PATH = os.environ.get("SLICE_PATH", "2009 Scanned Media/1978")

SLICE_DIR = MEDIA_ROOT / SLICE_PATH
AI_LAYER_DIR = MEDIA_ROOT / "_ai-layer"

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = REPO_ROOT / "private" / "slice_workspace"

# --- Inference ---
MODEL = "claude-sonnet-4-20250514"
PROMPT_VERSION = "photo_analysis_v1"
PROMPT_FILE = REPO_ROOT / "prompts" / f"{PROMPT_VERSION}.txt"

# --- Immich confidence thresholds ---
CONFIDENCE_HIGH = 0.8
CONFIDENCE_LOW = 0.5
