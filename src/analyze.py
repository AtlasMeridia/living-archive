"""Claude API vision calls for photo analysis."""

import base64
import json
import time
from pathlib import Path

import anthropic

from . import config


def load_prompt(folder_hint: str) -> str:
    """Load and format the analysis prompt."""
    template = config.PROMPT_FILE.read_text()
    return template.format(folder_hint=folder_hint)


def encode_image(path: Path) -> str:
    """Base64-encode a JPEG file."""
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def parse_json_response(text: str) -> dict:
    """Parse JSON from Claude's response, handling markdown fencing."""
    text = text.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` or ``` ... ```
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def analyze_photo(
    jpeg_path: Path,
    folder_hint: str,
    client: anthropic.Anthropic | None = None,
) -> tuple[dict, dict]:
    """Analyze a photo using Claude's vision API.

    Returns (analysis_dict, inference_metadata_dict).
    """
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
    analysis = parse_json_response(raw_text)

    inference_meta = {
        "model": config.MODEL,
        "prompt_version": config.PROMPT_VERSION,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    return analysis, inference_meta
