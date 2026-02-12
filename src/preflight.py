"""Preflight checks: NAS mount, Immich health, config validation."""

import logging
import subprocess
import sys
import time
from pathlib import Path

import httpx

from . import config

log = logging.getLogger("living_archive")


NAS_AFP_URL = "afp://mneme.local/MNEME"


def ensure_nas_mounted(
    mount_point: Path | None = None,
    auto_mount: bool = True,
    mount_attempts: int = 3,
) -> bool:
    """Ensure the NAS is mounted, retrying the mount command if needed.

    Uses macOS `open afp://` which triggers Finder mount with Keychain credentials.
    Retries the mount command up to `mount_attempts` times to handle NAS wake-up
    delays and transient network issues.

    Can be called from anywhere — preflight, mid-pipeline on I/O error, or standalone.
    """
    mount_point = mount_point or config.MEDIA_ROOT
    if mount_point.exists():
        log.info("  NAS mounted: %s", mount_point)
        return True

    if not auto_mount:
        log.error("  NAS not mounted: %s", mount_point)
        return False

    for attempt in range(1, mount_attempts + 1):
        log.info("  NAS not mounted. Auto-mount attempt %d/%d...", attempt, mount_attempts)
        try:
            subprocess.run(
                ["open", NAS_AFP_URL],
                check=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.warning("  Mount command failed: %s", e)
            if attempt < mount_attempts:
                time.sleep(5)
            continue

        # Wait for mount to appear (Finder mount is async)
        for i in range(15):
            time.sleep(2)
            if mount_point.exists():
                log.info("  NAS mounted after %.0fs: %s", (i + 1) * 2, mount_point)
                return True
            log.info("  Waiting for mount... (%ds)", (i + 1) * 2)

        if attempt < mount_attempts:
            log.warning("  Mount did not appear. Retrying...")

    log.error("  NAS did not mount after %d attempts.", mount_attempts)
    log.error("  Mount manually: Cmd+K in Finder → %s", NAS_AFP_URL)
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
            f"{url}/api/server/ping",
            headers={"x-api-key": api_key},
            timeout=5.0,
        )
        if resp.status_code == 200 and resp.json().get("res") == "pong":
            # Also check auth by hitting a protected endpoint
            auth_resp = httpx.get(
                f"{url}/api/server/version",
                headers={"x-api-key": api_key},
                timeout=5.0,
            )
            if auth_resp.status_code == 200:
                v = auth_resp.json()
                log.info("  Immich reachable: %s (v%s.%s.%s)",
                         url, v.get("major"), v.get("minor"), v.get("patch"))
                return True
            log.error("  Immich reachable but API key rejected (HTTP %d)", auth_resp.status_code)
            return False

        log.error("  Immich unexpected response: HTTP %d", resp.status_code)
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

    # 4. Inference backend
    if config.USE_CLI:
        if not config.CLAUDE_CLI.exists():
            log.error("  Claude CLI not found: %s", config.CLAUDE_CLI)
            all_ok = False
        else:
            log.info("  Claude CLI: %s (model: %s)", config.CLAUDE_CLI, config.CLI_MODEL)
    else:
        if not config.ANTHROPIC_API_KEY:
            log.error("  ANTHROPIC_API_KEY not set")
            all_ok = False
        else:
            log.info("  Anthropic API key: configured")

    # 5. Prompt file
    if not config.PROMPT_FILE.exists():
        log.error("  Prompt file not found: %s", config.PROMPT_FILE)
        all_ok = False
    else:
        log.info("  Prompt file: %s", config.PROMPT_FILE.name)

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
