"""Preflight checks: NAS mount, Immich health, config validation."""

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

from . import config

log = logging.getLogger("living_archive")


NAS_HOST = os.environ.get("NAS_HOST", "mneme.local")
NAS_SHARE = os.environ.get("NAS_SHARE", "MNEME")
NAS_USER = os.environ.get("NAS_USER", "living_archive_ro")
NAS_CREDENTIAL_ITEM = os.environ.get(
    "NAS_CREDENTIAL_ITEM",
    "MNEME Living Archive Read-Only",
)
AGENT_SECRET_BIN = os.environ.get(
    "AGENT_SECRET_BIN",
    str(Path.home() / ".local" / "bin" / "agent-secret"),
)


def _smb_url() -> str:
    """Build a non-secret SMB URL from conservative configuration values."""
    patterns = {
        "host": r"[A-Za-z0-9.-]+",
        "share": r"[A-Za-z0-9._ -]+",
        "user": r"[A-Za-z0-9._-]+",
    }
    values = {
        "host": NAS_HOST,
        "share": NAS_SHARE,
        "user": NAS_USER,
    }
    if any(not re.fullmatch(patterns[name], value) for name, value in values.items()):
        raise ValueError("invalid NAS mount configuration")
    return f"smb://{NAS_HOST}/{NAS_SHARE}"


def _get_nas_password() -> str | None:
    """Read the dedicated SMB password from 1Password without logging it."""
    if not re.fullmatch(r"[A-Za-z0-9 .()_-]+", NAS_CREDENTIAL_ITEM):
        return None
    try:
        result = subprocess.run(
            [AGENT_SECRET_BIN, "get", NAS_CREDENTIAL_ITEM, "--field", "password"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _applescript_string(value: str) -> str:
    """Escape a value for an AppleScript string literal."""
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("control character in mount credential")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _mount_script(smb_url: str, password: str) -> str:
    """Build the in-memory AppleScript supplied to osascript over stdin."""
    return (
        f'mount volume "{_applescript_string(smb_url)}" '
        f'as user name "{_applescript_string(NAS_USER)}" '
        f'with password "{_applescript_string(password)}"'
    )


def _mount_path_usable(path: Path, timeout: int = 5) -> bool:
    """Return True if the path exists and basic directory I/O succeeds quickly."""
    if not path.exists():
        return False
    try:
        result = subprocess.run(
            ["/bin/ls", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


_VOLUME_CONFIG_PATHS = (
    "DEFAULT_FAMILY_ROOT",
    "DEFAULT_PERSONAL_ROOT",
    "FAMILY_ROOT",
    "PERSONAL_ROOT",
    "MEDIA_ROOT",
    "SLICE_DIR",
    "DOCUMENTS_ROOT",
    "DOC_SLICE_DIR",
)


def _rebind_config_volume_paths(old_volume: Path, new_volume: Path) -> None:
    """Point imported config paths at a Finder-created volume alias."""
    for name in _VOLUME_CONFIG_PATHS:
        value = getattr(config, name, None)
        if not isinstance(value, Path):
            continue
        try:
            relative = value.relative_to(old_volume)
        except ValueError:
            continue
        setattr(config, name, new_volume / relative)


def _resolve_usable_mount_path(
    path: Path,
    volumes_dir: Path = Path("/Volumes"),
) -> Path | None:
    """Resolve a usable path, including Finder's MNEME-1 style aliases."""
    if _mount_path_usable(path):
        return path
    try:
        relative = path.relative_to(volumes_dir)
    except ValueError:
        return None
    if not relative.parts:
        return None

    volume_name = relative.parts[0]
    suffix = Path(*relative.parts[1:])
    old_volume = volumes_dir / volume_name
    alias_pattern = re.compile(rf"{re.escape(volume_name)}-\d+")
    for alternate in sorted(volumes_dir.glob(f"{volume_name}-*")):
        if not alias_pattern.fullmatch(alternate.name):
            continue
        candidate = alternate / suffix
        if _mount_path_usable(candidate):
            _rebind_config_volume_paths(old_volume, alternate)
            return candidate
    return None


def ensure_nas_mounted(
    mount_point: Path | None = None,
    auto_mount: bool = True,
    mount_attempts: int = 3,
) -> bool:
    """Ensure the NAS is mounted, retrying if needed.

    Uses Finder/NetFS through osascript. The dedicated read-only credential is
    retrieved from 1Password and supplied only as AppleScript on stdin. It is
    never placed in argv, a file, or application logs.
    Retries up to `mount_attempts` times to handle NAS wake-up delays.

    Can be called from anywhere — preflight, mid-pipeline on I/O error, or standalone.
    """
    mount_point = mount_point or config.MEDIA_ROOT
    usable_path = _resolve_usable_mount_path(mount_point)
    if usable_path is not None:
        log.info("  NAS mounted: %s", usable_path)
        return True
    if mount_point.exists():
        log.warning("  NAS path exists but is not readable: %s", mount_point)

    if not auto_mount:
        log.error("  NAS not mounted: %s", mount_point)
        return False

    try:
        smb_url = _smb_url()
    except ValueError:
        # Do not log values: malformed configuration could itself contain a
        # credential or injected AppleScript.
        log.error("  NAS mount configuration contains invalid characters.")
        return False

    password = _get_nas_password()
    if password is None:
        log.error("  NAS credential unavailable from the configured secret store.")
        return False
    try:
        mount_script = _mount_script(smb_url, password)
    except ValueError:
        log.error("  NAS credential contains unsupported control characters.")
        return False

    for attempt in range(1, mount_attempts + 1):
        log.info("  NAS not mounted. Auto-mount attempt %d/%d...", attempt, mount_attempts)
        try:
            result = subprocess.run(
                ["/usr/bin/osascript", "-"],
                input=mount_script,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            # Never log the exception object: TimeoutExpired includes argv.
            log.warning("  Mount command timed out after 30 seconds.")
            if attempt < mount_attempts:
                time.sleep(5)
            continue
        except FileNotFoundError:
            log.warning("  Mount command unavailable on this host.")
            if attempt < mount_attempts:
                time.sleep(5)
            continue
        if result.returncode != 0:
            # stderr is intentionally discarded because auth tools may echo
            # credential-bearing URLs in diagnostic output.
            log.warning("  Mount command failed (exit %d).", result.returncode)
            if attempt < mount_attempts:
                time.sleep(5)
            continue

        # Wait for mount to appear
        for i in range(10):
            time.sleep(2)
            usable_path = _resolve_usable_mount_path(mount_point)
            if usable_path is not None:
                log.info("  NAS mounted after %ds: %s", (i + 1) * 2, usable_path)
                return True
            log.info("  Waiting for mount... (%ds)", (i + 1) * 2)

        if attempt < mount_attempts:
            log.warning("  Mount did not appear. Retrying...")

    log.error("  NAS did not mount after %d attempts.", mount_attempts)
    log.error("  Mount manually: Cmd+K in Finder → smb://%s/%s", NAS_HOST, NAS_SHARE)
    return False


# Backward-compatible alias
check_nas_mount = ensure_nas_mounted


def check_immich(url: str | None = None, api_key: str | None = None) -> bool:
    """Ping the Immich server and verify API key works."""
    url = (url or config.IMMICH_URL).rstrip("/")
    api_key = api_key or config.IMMICH_API_KEY

    if not url or not api_key:
        log.error("  Immich not configured (IMMICH_URL or IMMICH_API_KEY missing)")
        return False

    try:
        resp = httpx.get(
            f"{url}/api/server/version",
            headers={"x-api-key": api_key},
            timeout=5.0,
        )
        if resp.status_code == 200:
            v = resp.json()
            log.info("  Immich reachable: %s (v%s.%s.%s)",
                     url, v.get("major"), v.get("minor"), v.get("patch"))
            return True
        log.error("  Immich reachable but API key rejected (HTTP %d)", resp.status_code)
        return False
    except httpx.ConnectError:
        log.error("  Immich unreachable: %s (connection refused)", url)
        return False
    except httpx.TimeoutException:
        log.error("  Immich unreachable: %s (timeout)", url)
        return False


def run_preflight(require_immich: bool = True) -> bool:
    """Run all preflight checks. Returns True if all pass.

    Args:
        require_immich: If False, Immich failure is a warning, not a blocker.
    """
    log.info("Preflight checks...")
    all_ok = True

    # 1. NAS mount
    if not check_nas_mount():
        all_ok = False

    # 2. Slice directory exists
    if all_ok and not config.SLICE_DIR.exists():
        log.error("  Slice directory not found: %s", config.SLICE_DIR)
        all_ok = False
    elif all_ok:
        log.info("  Slice directory: %s", config.SLICE_DIR)

    # 3. Immich
    immich_ok = check_immich()
    if not immich_ok:
        if require_immich:
            all_ok = False
        else:
            log.warning("  Immich not available — will skip metadata push")

    # 4. Inference backend (OAuth SDK / Max Plan)
    try:
        from .auth import resolve_token
        resolve_token()
        log.info("  OAuth token: configured (model: %s)", config.OAUTH_MODEL)
    except (ValueError, ImportError) as e:
        log.error("  OAuth token resolution failed: %s", e)
        all_ok = False

    # 5. Prompt file
    if not config.PROMPT_FILE.exists():
        log.error("  Prompt file not found: %s", config.PROMPT_FILE)
        all_ok = False
    else:
        log.info("  Prompt file: %s", config.PROMPT_FILE.name)

    # 6. Local data directory
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log.info("  Data dir: %s", config.DATA_DIR)

    # 7. Catalog (optional — informational only)
    if config.FAMILY_CATALOG_DB.exists():
        try:
            from .catalog import init_catalog
            conn = init_catalog(config.FAMILY_CATALOG_DB)
            conn.close()
            log.info("  Catalog: %s", config.FAMILY_CATALOG_DB.name)
        except Exception as e:
            log.warning("  Catalog check failed: %s", e)
    else:
        log.info("  Catalog: not yet created (run: python -m src.catalog backfill)")

    if all_ok:
        log.info("  All checks passed.")
    else:
        log.error("  Preflight failed. Fix the issues above and retry.")

    log.info("")
    return all_ok


def main():
    """CLI entry point: run preflight checks and report."""
    config.setup_logging()
    ok = run_preflight(require_immich=False)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
