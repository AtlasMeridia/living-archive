"""OAuth token management for Max Plan inference.

Resolves a usable Anthropic API credential from the Claude Code OAuth token,
avoiding per-token API billing. The token lookup chain:

  1. ANTHROPIC_API_KEY env var (standard API key — if set, use it directly)
  2. CLAUDE_CODE_OAUTH_TOKEN env var (Max Plan OAuth — zero marginal cost)
  3. Hermes env files (`~/.hermes/.env`, then `~/.hermes/profiles/*/.env`)

OAuth tokens (anything not starting with 'sk-ant-api') require Bearer auth
and Claude Code identity headers. This mirrors what Hermes does in
agent/anthropic_adapter.py — build_anthropic_client().
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

import anthropic
from httpx import Timeout

log = logging.getLogger("living_archive")

# Where Hermes stores the OAuth token
_HERMES_HOME = Path.home() / ".hermes"
_HERMES_ENV = _HERMES_HOME / ".env"

# Beta headers required for OAuth auth (matches Claude Code / Hermes)
_COMMON_BETAS = [
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
]
_OAUTH_BETAS = [
    "claude-code-20250219",
    "oauth-2025-04-20",
]


def _detect_claude_code_version() -> str:
    """Detect installed Claude Code version for user-agent header."""
    for cmd in ("claude", "claude-code"):
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                version = result.stdout.strip().split()[0]
                if version and version[0].isdigit():
                    return version
        except Exception:
            pass
    return "2.1.74"


def _is_oauth_token(key: str) -> bool:
    """Check if the key is an OAuth token (not a standard Console API key).

    Regular Console API keys start with 'sk-ant-api' and use x-api-key header.
    Everything else (OAuth setup-tokens 'sk-ant-oat*', managed keys, JWTs)
    requires Bearer auth + beta headers.
    """
    if not key:
        return False
    if key.startswith("sk-ant-api"):
        return False
    return True


def _hermes_env_candidates() -> list[Path]:
    """Search default Hermes env first, then named profile envs."""
    candidates: list[Path] = []
    if _HERMES_ENV.exists():
        candidates.append(_HERMES_ENV)
    profiles_dir = _HERMES_HOME / "profiles"
    if profiles_dir.exists():
        candidates.extend(sorted(profiles_dir.glob("*/.env")))
    return candidates


def _read_env_file_key(path: Path, key: str) -> str:
    """Read a key from a simple KEY=VALUE env file."""
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def _read_hermes_env(key: str) -> tuple[str, str]:
    """Read a key from Hermes env files. Returns (value, source_path)."""
    for env_path in _hermes_env_candidates():
        value = _read_env_file_key(env_path, key)
        if value:
            return value, str(env_path)
    return "", ""


def resolve_token() -> tuple[str, str]:
    """Resolve an Anthropic API credential.

    Returns (token, source) where source describes where it came from.
    Raises ValueError if no credential is found.
    """
    # 1. Standard API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        return api_key, "ANTHROPIC_API_KEY"

    # 2. OAuth token from env
    oauth = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if oauth:
        return oauth, "CLAUDE_CODE_OAUTH_TOKEN"

    # 3. OAuth token from Hermes env files (default profile or named profiles)
    oauth, source = _read_hermes_env("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth:
        return oauth, f"hermes:{source}"

    raise ValueError(
        "No Anthropic credential found. Set ANTHROPIC_API_KEY or "
        "CLAUDE_CODE_OAUTH_TOKEN, or ensure ~/.hermes/.env has it."
    )


def _build_client(token: str) -> anthropic.Anthropic:
    """Create an Anthropic client with correct auth for the token type.

    OAuth tokens get Bearer auth + Claude Code identity headers.
    Regular API keys get standard x-api-key auth.
    """
    kwargs = {
        "timeout": Timeout(timeout=300.0, connect=10.0),
    }

    if _is_oauth_token(token):
        # OAuth: Bearer auth + beta headers + Claude Code identity.
        # Without these, Anthropic rejects or intermittently 500s the request.
        version = _detect_claude_code_version()
        all_betas = _COMMON_BETAS + _OAUTH_BETAS
        kwargs["auth_token"] = token
        kwargs["default_headers"] = {
            "anthropic-beta": ",".join(all_betas),
            "user-agent": f"claude-cli/{version} (external, cli)",
            "x-app": "cli",
        }
        log.info("Anthropic auth: OAuth token (Bearer + Claude Code headers, v%s)", version)
    else:
        # Regular API key: x-api-key header
        kwargs["api_key"] = token
        if _COMMON_BETAS:
            kwargs["default_headers"] = {"anthropic-beta": ",".join(_COMMON_BETAS)}
        log.info("Anthropic auth: standard API key")

    return anthropic.Anthropic(**kwargs)


# Required system prompt prefix for OAuth routing — Anthropic's infra uses
# this to identify Claude Code traffic and route to Max Plan billing.
OAUTH_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."


# Module-level cached client
_client: Optional[anthropic.Anthropic] = None
_client_source: str = ""
_client_is_oauth: bool = False


def get_client() -> anthropic.Anthropic:
    """Return a cached Anthropic client using the resolved credential."""
    global _client, _client_source, _client_is_oauth
    if _client is not None:
        return _client

    token, source = resolve_token()
    _client = _build_client(token)
    _client_source = source
    _client_is_oauth = _is_oauth_token(token)
    return _client


def is_oauth() -> bool:
    """Return True if the current client is using OAuth (needs system prefix)."""
    return _client_is_oauth


def get_client_source() -> str:
    """Return the source of the current client's credential."""
    return _client_source
