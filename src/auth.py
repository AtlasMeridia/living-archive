"""OAuth token management for Max Plan inference.

Resolves a usable Anthropic API credential from the Claude Code OAuth token,
avoiding per-token API billing. The token lookup chain:

  1. ANTHROPIC_API_KEY env var (standard API key — if set, use it directly)
  2. CLAUDE_CODE_OAUTH_TOKEN env var (Max Plan OAuth — zero marginal cost)
  3. ~/.hermes/.env file (where Hermes stores it)

The OAuth token is passed directly as the API key to the Anthropic SDK —
Anthropic's API accepts it as a bearer token. No agent-key minting needed.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import anthropic

log = logging.getLogger("living_archive")

# Where Hermes stores the OAuth token
_HERMES_ENV = Path.home() / ".hermes" / ".env"


def _read_hermes_env(key: str) -> str:
    """Read a key from ~/.hermes/.env (simple KEY=VALUE format)."""
    if not _HERMES_ENV.exists():
        return ""
    for line in _HERMES_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


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

    # 3. OAuth token from Hermes env file
    oauth = _read_hermes_env("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth:
        return oauth, f"hermes:{_HERMES_ENV}"

    raise ValueError(
        "No Anthropic credential found. Set ANTHROPIC_API_KEY or "
        "CLAUDE_CODE_OAUTH_TOKEN, or ensure ~/.hermes/.env has it."
    )


# Module-level cached client
_client: Optional[anthropic.Anthropic] = None
_client_source: str = ""


def get_client() -> anthropic.Anthropic:
    """Return a cached Anthropic client using the resolved credential."""
    global _client, _client_source
    if _client is not None:
        return _client

    token, source = resolve_token()
    log.info("Anthropic auth: using %s", source)
    _client = anthropic.Anthropic(api_key=token)
    _client_source = source
    return _client


def get_client_source() -> str:
    """Return the source of the current client's credential."""
    return _client_source
