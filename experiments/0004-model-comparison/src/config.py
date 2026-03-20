"""Paths, CLI commands, model names for experiment 0004."""

import os
import subprocess
from pathlib import Path

# --- Paths ---
EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EXPERIMENT_ROOT.parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "data")))
CATALOG_DB = DATA_DIR / "catalog.db"
RUNS_DIR = EXPERIMENT_ROOT / "runs"

# NAS roots
FAMILY_ROOT = Path(os.environ.get(
    "FAMILY_ROOT", "/Volumes/MNEME/05_PROJECTS/Living Archive/Family"
))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(FAMILY_ROOT / "Media")))

# --- Prompts ---
PHOTO_PROMPT_FILE = REPO_ROOT / "prompts" / "photo_analysis_v1.txt"
DOC_PROMPT_FILE = REPO_ROOT / "prompts" / "document_analysis_v2.txt"
PHOTO_PROMPT_VERSION = "photo_analysis_v1"
DOC_PROMPT_VERSION = "document_analysis_v2"

# --- Extracted text for documents ---
DOC_EXTRACTED_TEXT_GLOB = "documents/runs/*/extracted-text"

# --- CLI tools ---
CLAUDE_CLI = Path(os.environ.get(
    "CLAUDE_CLI", os.path.expanduser("~/.local/bin/claude")
))
CODEX_CLI = Path(os.environ.get("CODEX_CLI", subprocess.run(
    ["which", "codex"], capture_output=True, text=True
).stdout.strip() or "codex"))

# --- Models ---
CLAUDE_MODEL = "opus"
GPT_MODEL = "gpt-5.4"

# --- Timeouts ---
PHOTO_TIMEOUT = 120  # seconds
DOC_TIMEOUT = 300    # seconds

# --- Batch processing ---
EST_SECONDS_PER_ASSET = 30  # for budget calculations

# --- Image conversion ---
MAX_EDGE = 2048
JPEG_QUALITY = 85

# --- Rate limit detection ---
RATE_LIMIT_SIGNALS = (
    "rate limit", "rate_limit", "429", "quota", "try again later",
    "overloaded", "capacity", "cooldown",
)
