"""Claude vision analysis via OAuth SDK (Max Plan)."""

import base64
import logging
from pathlib import Path

from . import config
from .inference import create_message, strip_json_fences
from .models import InferenceMetadata, PhotoAnalysis

log = logging.getLogger("living_archive")

__all__ = ["analyze_photo", "encode_image", "load_prompt", "strip_json_fences"]


def load_prompt(folder_hint: str) -> str:
    """Load and format the analysis prompt."""
    template = config.PROMPT_FILE.read_text()
    return template.format(folder_hint=folder_hint)


def encode_image(path: Path) -> str:
    """Base64-encode a JPEG file."""
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


@config.retry()
def analyze_photo(
    jpeg_path: Path,
    folder_hint: str,
) -> tuple[PhotoAnalysis, InferenceMetadata]:
    """Analyze a photo via the Anthropic SDK using Max Plan OAuth credentials."""
    prompt = load_prompt(folder_hint)
    image_data = encode_image(jpeg_path)

    response = create_message([
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
    ])

    raw_text = response.content[0].text
    analysis = PhotoAnalysis.model_validate_json(strip_json_fences(raw_text))

    inference_meta = InferenceMetadata(
        model=response.model,
        prompt_version=config.PROMPT_VERSION,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        raw_response=raw_text,
    )

    return analysis, inference_meta
