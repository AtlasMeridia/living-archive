"""Claude vision analysis: CLI mode (default) or direct API fallback."""

import base64
import json
import logging
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
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

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
        max_tokens=1024,
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


@config.retry()
def analyze_photo(
    jpeg_path: Path,
    folder_hint: str,
    client=None,
) -> tuple[PhotoAnalysis, InferenceMetadata]:
    """Analyze a photo using Claude.

    Dispatches to CLI mode (Max plan, no per-token cost) or API mode
    based on config.USE_CLI. Set USE_CLI=false in .env to use the API.
    """
    if config.USE_CLI:
        return _analyze_via_cli(jpeg_path, folder_hint)
    return _analyze_via_api(jpeg_path, folder_hint, client=client)
