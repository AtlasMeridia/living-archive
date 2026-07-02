"""Shared inference dispatch for the photo and document pipelines.

Primary backend is the Anthropic SDK on Max Plan OAuth. An experimental
Grok Build CLI backend (SuperGrok Heavy subscription) is exposed via
grok_structured() for A/B evaluation — see experiments/0008-grok-photo-pilot.
"""

import json
import os
import subprocess
from pathlib import Path

from . import config
from .auth import OAUTH_SYSTEM_PREFIX, get_client, is_oauth

GROK_BIN = Path.home() / ".grok" / "bin" / "grok"


def strip_json_fences(text: str) -> str:
    """Strip markdown code fences from a JSON response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def create_message(messages: list[dict]):
    """Send messages to Claude via the cached client (Max Plan OAuth aware).

    OAuth tokens require the Claude Code system prefix for Max Plan routing.
    Returns the raw Anthropic response.
    """
    client = get_client()

    kwargs = {}
    if is_oauth():
        kwargs["system"] = OAUTH_SYSTEM_PREFIX

    return client.messages.create(
        model=config.OAUTH_MODEL,
        max_tokens=4096,
        messages=messages,
        **kwargs,
    )


def grok_structured(prompt: str, schema: dict, cwd: Path, timeout: float = 300.0) -> dict:
    """Single-turn Grok Build headless call with schema-constrained JSON output.

    XAI_API_KEY is stripped from the environment — if present it silently
    overrides the SuperGrok subscription OAuth in ~/.grok/auth.json and
    bills the metered API instead.

    The agent runs with cwd set so it can Read local files (e.g. images)
    referenced in the prompt. Returns the parsed structuredOutput dict.
    """
    env = {k: v for k, v in os.environ.items() if k != "XAI_API_KEY"}
    result = subprocess.run(
        [str(GROK_BIN), "-p", prompt,
         "--json-schema", json.dumps(schema),
         "--always-approve"],
        capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"grok exited {result.returncode}: {result.stderr[-500:]}")

    stdout = result.stdout.strip()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        # Tolerate any preamble before the JSON envelope
        data = json.loads(stdout[stdout.index("{"):])

    out = data.get("structuredOutput")
    if out is None:
        raise ValueError(f"grok returned no structuredOutput: {stdout[:300]}")
    return out
