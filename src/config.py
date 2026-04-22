"""Path constants and environment variable loading."""

import functools
import logging
import os
import time as _time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _resolve_volume_alias(path_str: str) -> Path:
    """Resolve /Volumes/MNEME path aliases like MNEME-1, MNEME-2."""
    preferred = Path(path_str)
    if preferred.exists():
        return preferred
    parts = preferred.parts
    if len(parts) < 3 or parts[1] != 'Volumes':
        return preferred
    volume_name = parts[2]
    suffix = Path(*parts[3:]) if len(parts) > 3 else Path()
    volumes_dir = Path('/Volumes')
    for alt in sorted(volumes_dir.glob(f'{volume_name}*')):
        candidate = alt / suffix
        if candidate.exists():
            return candidate
    return preferred

# --- API keys ---
# ANTHROPIC_API_KEY is used by contact_triage.py for direct Haiku calls.
# The main photo/document pipelines use Max Plan OAuth via src/auth.py.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
IMMICH_API_KEY = os.environ.get("IMMICH_API_KEY", "")
IMMICH_URL = os.environ.get("IMMICH_URL", "http://mneme.local:2283")

# --- Paths: Branch roots ---
DEFAULT_FAMILY_ROOT = _resolve_volume_alias("/Volumes/MNEME/05_PROJECTS/Living Archive/Family")
DEFAULT_PERSONAL_ROOT = _resolve_volume_alias("/Volumes/MNEME/05_PROJECTS/Living Archive/Personal")
FAMILY_ROOT = Path(os.environ.get(
    "FAMILY_ROOT", str(DEFAULT_FAMILY_ROOT)
))
PERSONAL_ROOT = Path(os.environ.get(
    "PERSONAL_ROOT", str(DEFAULT_PERSONAL_ROOT)
))

# --- Paths: Photo pipeline ---
MEDIA_ROOT = Path(os.environ.get(
    "MEDIA_ROOT", str(FAMILY_ROOT / "Media")
))
SLICE_PATH = os.environ.get("SLICE_PATH", "2009 Scanned Media/1978")

SLICE_DIR = MEDIA_ROOT / SLICE_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Paths: AI layer (local, regeneratable) ---
DATA_DIR = Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "data")))
AI_LAYER_DIR = DATA_DIR / "photos"
DOC_AI_LAYER_DIR = DATA_DIR / "documents"
FAMILY_CATALOG_DB = DATA_DIR / "catalog.db"

# --- Style guide tokens ---
STYLE_GUIDE_ROOT = Path(os.environ.get(
    "STYLE_GUIDE_ROOT", os.path.expanduser("~/Projects/atlas-style-guide")
))
WORKSPACE_DIR = Path(os.environ.get(
    "WORKSPACE_DIR", str(REPO_ROOT / "private" / "slice_workspace")
))

# --- Paths: Document pipeline ---
DOCUMENTS_ROOT = Path(os.environ.get(
    "DOCUMENTS_ROOT", str(FAMILY_ROOT / "Documents")
))

DOC_SLICE_PATH = os.environ.get(
    "DOC_SLICE_PATH", "Liu Family Trust Filings & Documents"
)
_dsp = Path(DOC_SLICE_PATH)
DOC_SLICE_DIR = _dsp if _dsp.is_absolute() else DOCUMENTS_ROOT / DOC_SLICE_PATH

# --- Inference ---
# Both pipelines dispatch through the Anthropic SDK using a Max Plan OAuth
# token (see src/auth.py). Legacy Claude CLI, Codex CLI, Ollama, and direct
# API paths were removed on 2026-04-21 during the aggressive pare-down.
MODEL = "claude-sonnet-4-20250514"
OAUTH_MODEL = os.environ.get("OAUTH_MODEL", "claude-sonnet-4-20250514")
PROMPT_VERSION = "photo_analysis_v1"
PROMPT_FILE = REPO_ROOT / "prompts" / f"{PROMPT_VERSION}.txt"

DOC_PROMPT_VERSION = "document_analysis_v2"
DOC_PROMPT_FILE = REPO_ROOT / "prompts" / f"{DOC_PROMPT_VERSION}.txt"

# --- Batch / pacing controls ---
DOC_BATCH_SIZE = int(os.environ.get("DOC_BATCH_SIZE", "0"))        # 0 = unlimited
DOC_PACING_DELAY = float(os.environ.get("DOC_PACING_DELAY", "0"))  # seconds between docs

# --- Immich confidence thresholds ---
CONFIDENCE_HIGH = 0.8
CONFIDENCE_LOW = 0.5


def setup_logging() -> logging.Logger:
    """Configure and return the application logger.

    Console: INFO level, message-only format (preserves current UX).
    File: DEBUG level, timestamped, rotating 5MB/3 backups.
    """
    logger = logging.getLogger("living_archive")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    log_dir = REPO_ROOT / "private"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "living-archive.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
        logger.addHandler(file_handler)
    except OSError:
        pass  # Read-only filesystem (e.g. Docker container)

    return logger


def validate_photo_config() -> list[str]:
    """Check that photo pipeline config is valid. Returns list of error messages."""
    errors = []
    try:
        from .auth import resolve_token
        resolve_token()
    except ValueError as e:
        errors.append(str(e))
    if not MEDIA_ROOT.exists():
        errors.append(f"MEDIA_ROOT not found: {MEDIA_ROOT} (is the NAS mounted?)")
    if not PROMPT_FILE.exists():
        errors.append(f"Prompt file not found: {PROMPT_FILE}")
    return errors


def validate_doc_config() -> list[str]:
    """Check that document pipeline config is valid. Returns list of error messages."""
    errors = []
    try:
        from .auth import resolve_token
        resolve_token()
    except ValueError as e:
        errors.append(str(e))
    if not DOCUMENTS_ROOT.exists():
        errors.append(f"DOCUMENTS_ROOT not found: {DOCUMENTS_ROOT} (is the NAS mounted?)")
    if not DOC_PROMPT_FILE.exists():
        errors.append(f"Doc prompt file not found: {DOC_PROMPT_FILE}")
    return errors


def validate_immich_config() -> list[str]:
    """Check that Immich config is valid. Returns list of error messages."""
    errors = []
    if not IMMICH_API_KEY:
        errors.append("IMMICH_API_KEY is not set")
    if not IMMICH_URL:
        errors.append("IMMICH_URL is not set")
    return errors


# --- Retry decorator ---


_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = ()

def _get_retryable_exceptions() -> tuple[type[Exception], ...]:
    """Lazily build the set of retryable exceptions (anthropic SDK + httpx)."""
    global _RETRYABLE_EXCEPTIONS
    if _RETRYABLE_EXCEPTIONS:
        return _RETRYABLE_EXCEPTIONS
    import httpx
    import anthropic
    _RETRYABLE_EXCEPTIONS = (
        httpx.ConnectError,
        httpx.TimeoutException,
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
    )
    return _RETRYABLE_EXCEPTIONS


def _is_retryable_status(exc: Exception) -> bool:
    """Check if an HTTP status error has a retryable status code."""
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503)
    return False


def retry(max_attempts: int = 3, base_delay: float = 2.0, max_delay: float = 30.0):
    """Decorator for exponential-backoff retry on transient errors.

    Retries on: connection errors, timeouts, rate limits, 429/5xx.
    Does NOT retry on: 400/401/403 (config errors).
    """
    _log = logging.getLogger("living_archive")

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            retryable = _get_retryable_exceptions()
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except retryable as exc:
                    last_exc = exc
                except Exception as exc:
                    if _is_retryable_status(exc):
                        last_exc = exc
                    else:
                        raise
                if attempt < max_attempts:
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    _log.warning(
                        "Retry %d/%d for %s after %.1fs: %s",
                        attempt, max_attempts, fn.__name__, delay, last_exc,
                    )
                    _time.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator
