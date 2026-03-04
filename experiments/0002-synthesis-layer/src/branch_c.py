"""Branch C — LLM-assisted clustering.

Supports two reproducible execution modes:
1) inline (default): read curated clusters from a local JSON file that
   was produced during an interactive Claude session and human-reviewed.
2) anthropic: generate clusters directly via Anthropic API.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:  # pragma: no cover - optional dependency in inline mode
    anthropic = None

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs" / "p1-person-branches"
DEFAULT_RAW_NAMES = RUNS_DIR / "raw-names.json"
DEFAULT_OUTPUT = RUNS_DIR / "branch-c-clusters.json"
DEFAULT_INLINE_CLUSTERS = RUNS_DIR / "branch-c-inline-clusters.json"

# Only cluster names with >= this many mentions (reduces noise from one-off professionals)
MIN_MENTIONS = 2
DEFAULT_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are helping organize a family archive. You will receive a list of person names extracted from documents in a Chinese-American family's archive (immigration papers, financial documents, medical records, personal letters, etc.).

Many names refer to the same person but appear differently due to:
- Romanization variants of Chinese names (e.g., "Kuang" vs "Kang" for 光)
- Abbreviations (e.g., "F.K. Liu" vs "Feng Kuang Liu")
- Middle name inclusion/exclusion (e.g., "Meichu Grace Liu" vs "Meichu Liu")
- Maiden/married name combinations (e.g., "Y S Liu-Chen" vs "Chen Lee Fei Liu")
- Chinese characters alongside romanized names
- Partial names or titles ("Dr. Li", "Mom")
- Nicknames or shortened forms ("Grace Liu" vs "Meichu Grace Liu")

Group names that very likely refer to the same person into clusters. Each cluster should have a recommended canonical name (the most complete/formal version).

IMPORTANT:
- Only group names you are confident refer to the same person
- When in doubt, keep names separate (false negatives are better than false positives)
- Include Chinese-character names in clusters when they clearly match
- Preserve all original name strings exactly as given"""

USER_PROMPT_TEMPLATE = """Here are {count} person names extracted from a family archive. Each name is shown with its mention count.

Group names that refer to the same person. Return a JSON array of clusters:

```json
[
  {{
    "canonical": "Most complete version of the name",
    "canonical_zh": "Chinese characters if available, null otherwise",
    "variants": ["variant1", "variant2", ...],
    "confidence": 0.95,
    "reasoning": "Brief explanation of why these are the same person"
  }}
]
```

Only include clusters where you merged 2+ names. Names that don't match anyone else can be omitted.

THE NAMES:
{names}"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Branch C clustering workflow.")
    parser.add_argument(
        "--mode",
        choices=["inline", "anthropic"],
        default="inline",
        help="Execution mode. 'inline' reads curated local clusters; 'anthropic' calls API.",
    )
    parser.add_argument("--raw-names", type=Path, default=DEFAULT_RAW_NAMES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--inline-clusters", type=Path, default=DEFAULT_INLINE_CLUSTERS)
    parser.add_argument("--min-mentions", type=int, default=MIN_MENTIONS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    return parser.parse_args()


def load_names(path: Path, min_mentions: int) -> tuple[dict, dict]:
    raw = json.loads(path.read_text())
    frequent = {name: count for name, count in raw["names"].items() if count >= min_mentions}
    return raw, frequent


def run_inline(inline_clusters_path: Path) -> tuple[list[dict], dict]:
    if not inline_clusters_path.exists():
        print(
            f"ERROR: Inline clusters file not found: {inline_clusters_path}\n"
            "Provide --inline-clusters with a curated clusters JSON file.",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = json.loads(inline_clusters_path.read_text())
    if isinstance(payload, list):
        clusters = payload
        metadata = {}
    elif isinstance(payload, dict) and isinstance(payload.get("clusters"), list):
        clusters = payload["clusters"]
        metadata = payload
    else:
        print(
            "ERROR: Inline clusters JSON must be either a cluster array or "
            "an object with a 'clusters' array.",
            file=sys.stderr,
        )
        sys.exit(1)

    return clusters, metadata


def run_anthropic(frequent: dict, model: str, min_mentions: int) -> tuple[list[dict], dict]:
    if anthropic is None:
        print("ERROR: anthropic package is required for --mode anthropic", file=sys.stderr)
        sys.exit(1)

    name_lines = []
    for name in sorted(frequent.keys(), key=lambda n: n.lower()):
        name_lines.append(f"  {frequent[name]:3d}x  {name}")
    prompt = USER_PROMPT_TEMPLATE.format(count=len(frequent), names="\n".join(name_lines))

    print(f"Sending {len(frequent)} names (>={min_mentions} mentions) to Claude...")
    print(f"Prompt length: {len(prompt)} chars")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    json_start = text.find("[")
    json_end = text.rfind("]") + 1
    if json_start == -1 or json_end == 0:
        print("ERROR: No JSON array found in response", file=sys.stderr)
        print(text)
        sys.exit(1)

    clusters = json.loads(text[json_start:json_end])
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return clusters, {"usage": usage}


def main():
    args = parse_args()
    raw, frequent = load_names(args.raw_names, args.min_mentions)

    if args.mode == "inline":
        clusters, metadata = run_inline(args.inline_clusters)
        model = metadata.get("model", "claude-opus-4-6 (inline session)")
        note = metadata.get(
            "note",
            "Clusters sourced from an interactive Claude session and human-reviewed.",
        )
    else:
        clusters, metadata = run_anthropic(frequent, args.model, args.min_mentions)
        model = args.model
        note = None

    total_variants = sum(len(c["variants"]) for c in clusters)
    result = {
        "branch": "C",
        "method": "llm_clustering",
        "execution_mode": args.mode,
        "model": model,
        "input_count": len(raw["names"]),
        "filtered_input_count": len(frequent),
        "min_mentions_filter": args.min_mentions,
        "cluster_count": len(clusters),
        "total_variants_merged": total_variants,
        "clusters": clusters,
    }
    if note:
        result["note"] = note
    if "usage" in metadata:
        result["usage"] = metadata["usage"]

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Branch C [{args.mode}]: {len(clusters)} clusters, {total_variants} total variants")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
