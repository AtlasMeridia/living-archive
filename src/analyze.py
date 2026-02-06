"""Claude API vision calls for photo analysis."""

import base64
from pathlib import Path

import anthropic

from . import config
from .models import InferenceMetadata, PhotoAnalysis


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


@config.retry()
def analyze_photo(
    jpeg_path: Path,
    folder_hint: str,
    client: anthropic.Anthropic | None = None,
) -> tuple[PhotoAnalysis, InferenceMetadata]:
    """Analyze a photo using Claude's vision API.

    Returns (PhotoAnalysis, InferenceMetadata).
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
