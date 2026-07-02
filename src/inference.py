"""Shared Anthropic inference dispatch for the photo and document pipelines."""

from . import config
from .auth import OAUTH_SYSTEM_PREFIX, get_client, is_oauth


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
