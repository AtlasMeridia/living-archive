"""Branch C — LLM-assisted clustering.

Feeds all unique key_people strings to Claude in one call to group
names that likely refer to the same person. Focuses on high-frequency
names (>=2 mentions) to keep the prompt manageable and the task focused
on names where dedup actually matters.
"""

import json
import sys
from pathlib import Path

import anthropic

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs" / "p1-person-branches"

# Only cluster names with >= this many mentions (reduces noise from one-off professionals)
MIN_MENTIONS = 2

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


def main():
    raw = json.loads((RUNS_DIR / "raw-names.json").read_text())

    # Filter to names with >= MIN_MENTIONS
    frequent = {name: count for name, count in raw["names"].items() if count >= MIN_MENTIONS}

    # Format for prompt
    name_lines = []
    for name in sorted(frequent.keys(), key=lambda n: n.lower()):
        name_lines.append(f"  {frequent[name]:3d}x  {name}")

    prompt = USER_PROMPT_TEMPLATE.format(
        count=len(frequent),
        names="\n".join(name_lines),
    )

    print(f"Sending {len(frequent)} names (>={MIN_MENTIONS} mentions) to Claude...")
    print(f"Prompt length: {len(prompt)} chars")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract JSON from response
    text = response.content[0].text
    print(f"\nResponse tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out")

    # Parse the JSON from the response (may be wrapped in ```json ... ```)
    json_start = text.find("[")
    json_end = text.rfind("]") + 1
    if json_start == -1 or json_end == 0:
        print("ERROR: No JSON array found in response")
        print(text)
        sys.exit(1)

    clusters = json.loads(text[json_start:json_end])

    # Count variants
    total_variants = sum(len(c["variants"]) for c in clusters)

    result = {
        "branch": "C",
        "method": "llm_clustering",
        "model": "claude-sonnet-4-20250514",
        "input_count": len(raw["names"]),
        "filtered_input_count": len(frequent),
        "min_mentions_filter": MIN_MENTIONS,
        "cluster_count": len(clusters),
        "total_variants_merged": total_variants,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "clusters": clusters,
    }

    out = RUNS_DIR / "branch-c-clusters.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nBranch C: {len(clusters)} clusters, {total_variants} total variants")
    print(f"Output: {out}")

    # Print clusters for review
    print("\n--- LLM clusters ---")
    for c in clusters:
        zh = f" / {c['canonical_zh']}" if c.get("canonical_zh") else ""
        print(f"\n  [{c['canonical']}{zh}] (confidence: {c['confidence']})")
        print(f"    Reasoning: {c['reasoning']}")
        for v in c["variants"]:
            print(f"    - {v}")


if __name__ == "__main__":
    main()
