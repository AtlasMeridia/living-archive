"""Claude vision analysis: OAuth SDK (default), CLI, or direct API."""

import base64
import json
import logging
import os
import subprocess
from pathlib import Path

from . import config
from .models import InferenceMetadata, PhotoAnalysis

log = logging.getLogger("living_archive")


def load_prompt(folder_hint: str) -> str:
    """Load and format the analysis prompt."""
    template = config.PROMPT_FILE.read_text()
    return template.format(folder_hint=folder_hint)


def encode_image(path: Path) -> str:
    """Base64-encode a JPEG file."""
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


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


def _photo_analysis_schema() -> str:
    """Auto-generate JSON Schema from the PhotoAnalysis Pydantic model."""
    return json.dumps(PhotoAnalysis.model_json_schema())


def _build_cli_prompt(jpeg_path: Path, folder_hint: str) -> str:
    """Build prompt for CLI mode: instructs Claude to read the image file."""
    base_prompt = load_prompt(folder_hint)
    return f"Read and analyze the photo at: {jpeg_path.resolve()}\n\n{base_prompt}"


# ---------------------------------------------------------------------------
# OAuth mode — Anthropic SDK with Max Plan token (zero marginal cost)
# ---------------------------------------------------------------------------


def _analyze_via_oauth(
    jpeg_path: Path,
    folder_hint: str,
) -> tuple[PhotoAnalysis, InferenceMetadata]:
    """Analyze a photo via the Anthropic SDK using OAuth credentials.

    Uses the Max Plan OAuth token — same token pool as Claude CLI,
    but without subprocess overhead or CLI hook fragility.
    """
    from .auth import get_client

    client = get_client()
    prompt = load_prompt(folder_hint)
    image_data = encode_image(jpeg_path)

    response = client.messages.create(
        model=config.OAUTH_MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw_text = response.content[0].text
    clean_json = strip_json_fences(raw_text)
    analysis = PhotoAnalysis.model_validate_json(clean_json)

    inference_meta = InferenceMetadata(
        model=response.model,
        prompt_version=config.PROMPT_VERSION,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        raw_response=raw_text,
    )

    return analysis, inference_meta


# ---------------------------------------------------------------------------
# CLI mode — Claude Code CLI subprocess (legacy, also uses Max Plan)
# ---------------------------------------------------------------------------


def _analyze_via_cli(
    jpeg_path: Path,
    folder_hint: str,
) -> tuple[PhotoAnalysis, InferenceMetadata]:
    """Analyze a photo via the Claude Code CLI (uses Max plan)."""
    prompt = _build_cli_prompt(jpeg_path, folder_hint)
    schema = _photo_analysis_schema()

    cmd = [
        str(config.CLAUDE_CLI), "-p", prompt,
        "--output-format", "json",
        "--json-schema", schema,
        "--model", config.CLI_MODEL,
        "--allowedTools", "Read",
        "--no-session-persistence",
    ]

    log.debug("CLI command: %s", " ".join(cmd[:4]) + " ...")
    # Strip env vars that cause issues in subprocess
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_PLUGIN_ROOT")}
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)

    if result.returncode != 0:
        raise RuntimeError(
            f"Claude CLI exited with code {result.returncode}: "
            f"{result.stderr[:500] if result.stderr else 'no stderr'}"
        )

    envelope = json.loads(result.stdout)
    analysis = PhotoAnalysis.model_validate(envelope["structured_output"])

    # Extract token usage from CLI envelope
    usage = envelope.get("usage", {})
    model_used = envelope.get("model", config.CLI_MODEL)

    inference_meta = InferenceMetadata(
        model=model_used,
        prompt_version=config.PROMPT_VERSION,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        raw_response=json.dumps(envelope.get("structured_output", {})),
    )

    return analysis, inference_meta


# ---------------------------------------------------------------------------
# API mode — Anthropic SDK with standard API key (billed per-token)
# ---------------------------------------------------------------------------


def _analyze_via_api(
    jpeg_path: Path,
    folder_hint: str,
    client=None,
) -> tuple[PhotoAnalysis, InferenceMetadata]:
    """Analyze a photo via the Anthropic API (billed per-token)."""
    import anthropic

    if client is None:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = load_prompt(folder_hint)
    image_data = encode_image(jpeg_path)

    response = client.messages.create(
        model=config.MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw_text = response.content[0].text
    clean_json = strip_json_fences(raw_text)
    analysis = PhotoAnalysis.model_validate_json(clean_json)

    inference_meta = InferenceMetadata(
        model=config.MODEL,
        prompt_version=config.PROMPT_VERSION,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        raw_response=raw_text,
    )

    return analysis, inference_meta


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@config.retry()
def analyze_photo(
    jpeg_path: Path,
    folder_hint: str,
    client=None,
) -> tuple[PhotoAnalysis, InferenceMetadata]:
    """Analyze a photo using Claude.

    Dispatches based on config.INFERENCE_MODE:
      - "oauth": SDK + Max Plan OAuth token (default, zero marginal cost)
      - "cli":   Claude Code CLI subprocess (legacy, also Max Plan)
      - "api":   SDK + standard API key (billed per-token)
    """
    if config.INFERENCE_MODE == "oauth":
        return _analyze_via_oauth(jpeg_path, folder_hint)
    elif config.INFERENCE_MODE == "cli":
        return _analyze_via_cli(jpeg_path, folder_hint)
    return _analyze_via_api(jpeg_path, folder_hint, client=client)
