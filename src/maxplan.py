"""Max Plan inference — zero-marginal-cost Claude via OAuth token.

Shared library for using Claude Max Plan subscription tokens programmatically
through the Anthropic Python SDK. Handles OAuth token resolution, Bearer auth,
Claude Code identity headers, and provides convenience wrappers for common
call patterns (text, vision, structured output).

Falls back to Claude CLI subprocess when INFERENCE_MODE=cli.

Usage:
    from maxplan import client, call, call_vision

    # Auto-resolves OAuth token, builds correct client
    c = client()

    # Convenience wrappers
    result = call("Analyze this", model="sonnet", schema=MyModel)
    text = call("Summarize this")
    result = call_vision("photo.jpg", "Describe this photo")

Token resolution (first found wins):
    1. ANTHROPIC_API_KEY env var (standard Console key)
    2. CLAUDE_CODE_OAUTH_TOKEN env var
    3. CLAUDE_CODE_OAUTH_TOKEN from Hermes env files (~/.hermes/.env, then ~/.hermes/profiles/*/.env)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HERMES_HOME = Path.home() / ".hermes"
_HERMES_ENV = _HERMES_HOME / ".env"

# Beta headers (matches Claude Code / Hermes adapter)
_COMMON_BETAS = [
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
]
_OAUTH_BETAS = [
    "claude-code-20250219",
    "oauth-2025-04-20",
]

# Required for OAuth requests to route to Max Plan billing
SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."

# Rate limit signals for CLI fallback
_RATE_LIMIT_SIGNALS = (
    "rate limit", "rate_limit", "429", "quota", "try again later",
    "overloaded", "capacity", "cooldown",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MaxPlanError(RuntimeError):
    """Base error for maxplan-inference."""


class AuthError(MaxPlanError):
    """No usable credential found."""


class RateLimitError(MaxPlanError):
    """Rate limit or capacity issue."""


class CliError(MaxPlanError):
    """Claude CLI subprocess failed."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Result:
    """Structured result from a Claude call."""
    output: Any          # dict (structured), str (text), or Pydantic instance
    model: str           # model that ran
    input_tokens: int    # input token count
    output_tokens: int   # output token count
    raw: Any = None      # raw API response or CLI envelope


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------


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


def _is_oauth_token(key: str) -> bool:
    """Check if the key is OAuth (not a standard Console API key).

    Console API keys start with 'sk-ant-api' and use x-api-key header.
    Everything else (OAuth tokens, setup tokens, managed keys) needs
    Bearer auth + identity headers.
    """
    if not key:
        return False
    return not key.startswith("sk-ant-api")


def resolve_token() -> tuple[str, str]:
    """Resolve an Anthropic credential. Returns (token, source).

    Raises AuthError if no credential is found.
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

    raise AuthError(
        "No Anthropic credential found. Set ANTHROPIC_API_KEY or "
        "CLAUDE_CODE_OAUTH_TOKEN, or ensure ~/.hermes/.env has it."
    )


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


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


def _build_client(token: str):
    """Create an Anthropic client with correct auth for the token type."""
    import anthropic
    from httpx import Timeout

    kwargs = {
        "timeout": Timeout(timeout=300.0, connect=10.0),
    }

    if _is_oauth_token(token):
        version = _detect_claude_code_version()
        all_betas = _COMMON_BETAS + _OAUTH_BETAS
        kwargs["auth_token"] = token
        kwargs["default_headers"] = {
            "anthropic-beta": ",".join(all_betas),
            "user-agent": f"claude-cli/{version} (external, cli)",
            "x-app": "cli",
        }
        log.info("maxplan: OAuth token (v%s)", version)
    else:
        kwargs["api_key"] = token
        if _COMMON_BETAS:
            kwargs["default_headers"] = {"anthropic-beta": ",".join(_COMMON_BETAS)}
        log.info("maxplan: standard API key")

    return anthropic.Anthropic(**kwargs)


# Module-level cached client
_client = None
_client_source: str = ""
_client_is_oauth: bool = False


def client():
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
    """Return True if the current client is using OAuth."""
    return _client_is_oauth


def reset_client():
    """Clear the cached client (useful for testing)."""
    global _client, _client_source, _client_is_oauth
    _client = None
    _client_source = ""
    _client_is_oauth = False


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def _schema_to_json(schema) -> str | None:
    """Convert a schema argument to a JSON string.

    Accepts: Pydantic model class, dict, JSON string, or None.
    """
    if schema is None:
        return None
    if hasattr(schema, "model_json_schema"):
        return json.dumps(schema.model_json_schema())
    if isinstance(schema, dict):
        return json.dumps(schema)
    if isinstance(schema, str):
        json.loads(schema)  # validate
        return schema
    raise TypeError(f"Unsupported schema type: {type(schema)}")


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences from a JSON response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


# ---------------------------------------------------------------------------
# SDK call (OAuth / API key)
# ---------------------------------------------------------------------------


def call(
    prompt: str,
    *,
    model: str = "claude-sonnet-4-20250514",
    schema=None,
    system: str | None = None,
    max_tokens: int = 4096,
    image: str | Path | None = None,
    image_media_type: str = "image/jpeg",
) -> Result:
    """Call Claude via the Anthropic SDK using Max Plan tokens.

    Args:
        prompt: User prompt text.
        model: Model ID (default: claude-sonnet-4-20250514).
        schema: Pydantic model class, dict, or JSON string for structured output.
            The model is instructed to return JSON matching this schema.
        system: System prompt (OAuth prefix is prepended automatically).
        max_tokens: Max output tokens.
        image: Path to image file or base64 string for vision calls.
        image_media_type: MIME type for the image (default: image/jpeg).

    Returns:
        Result with output (dict if schema, str if text), model, token counts.
    """
    c = client()

    # Build system prompt — OAuth needs the Claude Code prefix
    system_parts = []
    if _client_is_oauth:
        system_parts.append(SYSTEM_PREFIX)
    if system:
        system_parts.append(system)
    system_text = "\n\n".join(system_parts) if system_parts else None

    # Build message content
    content = []
    if image is not None:
        image_path = Path(image) if not isinstance(image, str) or not image.startswith("/9j/") else None
        if image_path and image_path.exists():
            image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
        else:
            image_data = image  # assume already base64
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_media_type,
                "data": image_data,
            },
        })

    # Add schema instruction to prompt if structured output requested
    prompt_text = prompt
    if schema is not None:
        schema_json = _schema_to_json(schema)
        prompt_text = (
            f"{prompt}\n\nRespond with a JSON object matching this schema "
            f"(no markdown fences, no explanation):\n{schema_json}"
        )

    content.append({"type": "text", "text": prompt_text})

    # Build API call kwargs
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system_text:
        kwargs["system"] = system_text

    response = c.messages.create(**kwargs)
    raw_text = response.content[0].text

    # Parse output
    if schema is not None:
        clean = _strip_json_fences(raw_text)
        output = json.loads(clean)
        # If schema is a Pydantic model, validate
        if hasattr(schema, "model_validate"):
            output = schema.model_validate(output)
    else:
        output = raw_text

    return Result(
        output=output,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        raw=response,
    )


def call_vision(
    image: str | Path,
    prompt: str,
    *,
    model: str = "claude-sonnet-4-20250514",
    schema=None,
    system: str | None = None,
    max_tokens: int = 4096,
    image_media_type: str = "image/jpeg",
) -> Result:
    """Convenience wrapper for vision calls. Same as call() with image first."""
    return call(
        prompt,
        model=model,
        schema=schema,
        system=system,
        max_tokens=max_tokens,
        image=image,
        image_media_type=image_media_type,
    )


# ---------------------------------------------------------------------------
# CLI fallback
# ---------------------------------------------------------------------------


def call_cli(
    prompt: str,
    *,
    model: str = "sonnet",
    schema=None,
    system: str | None = None,
    tools: list[str] | None = None,
    timeout: int = 300,
    max_retries: int = 3,
    base_delay: float = 2.0,
    rate_limit_delay: float = 60.0,
    cli_path: str | None = None,
) -> Result:
    """Call Claude via the CLI binary (legacy fallback).

    Uses Max Plan tokens through the CLI's own OAuth handling.
    Slower (process spawn per call) but doesn't require SDK setup.
    """
    cli = cli_path or os.environ.get(
        "CLAUDE_CLI", os.path.expanduser("~/.local/bin/claude")
    )
    schema_json = _schema_to_json(schema)

    cmd = [cli, "-p", prompt, "--output-format", "json"]
    if schema_json:
        cmd.extend(["--json-schema", schema_json])
    if model:
        cmd.extend(["--model", model])
    if system:
        cmd.extend(["--system-prompt", system])
    if tools:
        cmd.extend(["--allowedTools", ",".join(tools)])
    cmd.append("--no-session-persistence")

    # Strip env vars that cause subprocess issues
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("CLAUDECODE", "CLAUDE_PLUGIN_ROOT")
    }

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, env=env,
            )

            if result.returncode != 0:
                stderr = result.stderr[:500] if result.stderr else "no stderr"
                msg = f"Claude CLI exited {result.returncode}: {stderr}"
                if result.stderr and any(
                    s in result.stderr.lower() for s in _RATE_LIMIT_SIGNALS
                ):
                    raise RateLimitError(msg)
                raise CliError(msg)

            envelope = json.loads(result.stdout)

            if schema_json and "structured_output" in envelope:
                output = envelope["structured_output"]
            else:
                # Extract text from envelope
                if "result" in envelope:
                    output = envelope["result"]
                else:
                    content = envelope.get("content", [])
                    if isinstance(content, list):
                        parts = [
                            b.get("text", "")
                            for b in content if b.get("type") == "text"
                        ]
                        output = "\n".join(parts) if parts else ""
                    else:
                        output = ""

            usage = envelope.get("usage", {})
            return Result(
                output=output,
                model=envelope.get("model", model),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                raw=envelope,
            )

        except RateLimitError as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                log.warning(
                    "Rate limited (%d/%d), waiting %.0fs",
                    attempt + 1, max_retries, rate_limit_delay,
                )
                time.sleep(rate_limit_delay)

        except (CliError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, exc)
                time.sleep(delay)

    raise last_exc  # type: ignore[misc]
