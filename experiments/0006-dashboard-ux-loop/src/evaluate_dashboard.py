"""Dashboard UX evaluator — screenshot + vision LLM scoring.

Takes screenshots of the dashboard at multiple viewports and scores
each against a UX rubric using a vision model.

Requires: playwright (for screenshots), maxplan (for vision scoring)

Usage:
    python evaluate_dashboard.py                    # score all viewports
    python evaluate_dashboard.py --url http://...   # custom URL
    python evaluate_dashboard.py --tab ask          # score specific tab
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Add maxplan
sys.path.insert(0, str(Path.home() / "Projects" / "tools" / "maxplan-inference"))
import maxplan

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"

VIEWPORTS = {
    "mobile":  {"width": 375,  "height": 812},
    "tablet":  {"width": 768,  "height": 1024},
    "desktop": {"width": 1280, "height": 800},
}

TABS = ["ask", "overview"]  # tabs to evaluate (expandable)

RUBRIC = """Score this dashboard screenshot on a scale of 0.0 to 1.0 for each criterion.
The viewport is VIEWPORT_NAME (VIEWPORT_WIDTHpx × VIEWPORT_HEIGHTpx). The active tab is TAB_NAME.

CRITERIA:
1. layout_integrity: No overflow, no hidden content, no overlapping elements, proper spacing.
   1.0 = everything visible and well-placed. 0.0 = content hidden, overlapping, or clipped.

2. readability: Text is legible, clear visual hierarchy (headings > body > labels), appropriate font sizes.
   1.0 = easy to read, clear hierarchy. 0.0 = text too small, truncated, or no hierarchy.

3. navigation: All tabs/buttons are reachable and clearly labeled. Active state is obvious.
   1.0 = navigation is intuitive and complete. 0.0 = tabs hidden, cut off, or unlabeled.

4. info_density: Good use of available space — data is visible, not wasted empty areas or overwhelming clutter.
   1.0 = balanced density. 0.0 = mostly empty or overwhelmingly dense.

5. mobile_ux: (Only for mobile/tablet) Touch targets >= 44px, no horizontal scroll needed, native mobile feel.
   For desktop, score general usability instead.
   1.0 = feels native to the device. 0.0 = desktop site forced onto small screen.

Return ONLY a JSON object:
{
  "layout_integrity": 0.X,
  "readability": 0.X,
  "navigation": 0.X,
  "info_density": 0.X,
  "mobile_ux": 0.X,
  "overall": 0.X,
  "issues": ["issue 1", "issue 2"],
  "strengths": ["strength 1"]
}"""


@dataclass
class ViewportScore:
    viewport: str
    tab: str
    layout_integrity: float = 0.0
    readability: float = 0.0
    navigation: float = 0.0
    info_density: float = 0.0
    mobile_ux: float = 0.0
    overall: float = 0.0
    issues: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    screenshot_path: str = ""


def screenshot_dashboard(
    url: str,
    viewport: dict,
    output_path: Path,
    tab: str = "ask",
) -> bool:
    """Take a screenshot of the dashboard at a specific viewport using npx playwright."""
    # Add tab hash to URL so we land on the right tab
    target_url = f"{url}#{tab}" if tab != "ask" else url

    result = subprocess.run(
        [
            "npx", "playwright", "screenshot",
            f"--viewport-size={viewport['width']},{viewport['height']}",
            "--wait-for-timeout=2000",
            target_url,
            str(output_path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"  Screenshot failed: {result.stderr[:200]}")
        return False
    return output_path.exists()


def score_screenshot(
    screenshot_path: Path,
    viewport_name: str,
    viewport: dict,
    tab: str,
) -> ViewportScore:
    """Score a screenshot using vision LLM."""
    prompt = RUBRIC.replace("VIEWPORT_NAME", viewport_name) \
                    .replace("VIEWPORT_WIDTH", str(viewport["width"])) \
                    .replace("VIEWPORT_HEIGHT", str(viewport["height"])) \
                    .replace("TAB_NAME", tab)

    result = maxplan.call_vision(
        str(screenshot_path),
        prompt,
        model="claude-sonnet-4-20250514",
        max_tokens=500,
    )

    try:
        # Strip markdown fences
        text = result.output.strip()
        if text.startswith("```"):
            lines = text.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        print(f"  Failed to parse score: {result.output[:200]}")
        return ViewportScore(viewport=viewport_name, tab=tab)

    return ViewportScore(
        viewport=viewport_name,
        tab=tab,
        layout_integrity=float(data.get("layout_integrity", 0)),
        readability=float(data.get("readability", 0)),
        navigation=float(data.get("navigation", 0)),
        info_density=float(data.get("info_density", 0)),
        mobile_ux=float(data.get("mobile_ux", 0)),
        overall=float(data.get("overall", 0)),
        issues=data.get("issues", []),
        strengths=data.get("strengths", []),
        screenshot_path=str(screenshot_path),
    )


def evaluate_all(
    url: str = "http://localhost:8378",
    tabs: list[str] = None,
    viewports: dict = None,
) -> list[ViewportScore]:
    """Run full evaluation across viewports and tabs."""
    tabs = tabs or TABS
    viewports = viewports or VIEWPORTS

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    screenshot_dir = RUNS_DIR / "screenshots" / timestamp
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    scores = []
    for tab in tabs:
        for vp_name, vp_size in viewports.items():
            print(f"  [{tab}@{vp_name}] Screenshotting {vp_size['width']}×{vp_size['height']}...")
            img_path = screenshot_dir / f"{tab}_{vp_name}.png"

            if not screenshot_dashboard(url, vp_size, img_path, tab):
                print(f"  [{tab}@{vp_name}] Screenshot failed, skipping")
                continue

            print(f"  [{tab}@{vp_name}] Scoring...")
            score = score_screenshot(img_path, vp_name, vp_size, tab)
            score.screenshot_path = str(img_path)
            scores.append(score)

            print(f"  [{tab}@{vp_name}] Score: {score.overall:.2f} "
                  f"(layout={score.layout_integrity:.1f} read={score.readability:.1f} "
                  f"nav={score.navigation:.1f} density={score.info_density:.1f} "
                  f"mobile={score.mobile_ux:.1f})")
            if score.issues:
                for issue in score.issues[:3]:
                    print(f"    ⚠ {issue}")

    return scores


def save_scores(scores: list[ViewportScore], label: str = ""):
    """Save evaluation results."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = RUNS_DIR / "evaluations"
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"eval_{label}_{timestamp}.json" if label else f"eval_{timestamp}.json"

    data = {
        "timestamp": timestamp,
        "label": label,
        "scores": [
            {
                "viewport": s.viewport,
                "tab": s.tab,
                "layout_integrity": s.layout_integrity,
                "readability": s.readability,
                "navigation": s.navigation,
                "info_density": s.info_density,
                "mobile_ux": s.mobile_ux,
                "overall": s.overall,
                "issues": s.issues,
                "strengths": s.strengths,
            }
            for s in scores
        ],
        "summary": {
            "overall_avg": round(sum(s.overall for s in scores) / max(1, len(scores)), 3),
            "by_viewport": {
                vp: round(
                    sum(s.overall for s in scores if s.viewport == vp) /
                    max(1, len([s for s in scores if s.viewport == vp])),
                    3
                )
                for vp in set(s.viewport for s in scores)
            },
        },
    }

    with open(out_dir / filename, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to {out_dir / filename}")
    return data


def print_summary(scores: list[ViewportScore]):
    """Print evaluation summary."""
    print(f"\n{'Tab':<10} {'Viewport':<10} {'Layout':>7} {'Read':>7} {'Nav':>7} {'Density':>7} {'Mobile':>7} {'TOTAL':>7}")
    print("-" * 65)
    for s in scores:
        print(f"{s.tab:<10} {s.viewport:<10} {s.layout_integrity:>7.2f} {s.readability:>7.2f} "
              f"{s.navigation:>7.2f} {s.info_density:>7.2f} {s.mobile_ux:>7.2f} {s.overall:>7.2f}")

    # Averages
    if scores:
        avg = sum(s.overall for s in scores) / len(scores)
        print("-" * 65)
        print(f"{'AVG':<10} {'ALL':<10} {'':>7} {'':>7} {'':>7} {'':>7} {'':>7} {avg:>7.3f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8378")
    parser.add_argument("--tab", nargs="+", default=TABS)
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()

    print(f"Dashboard UX Evaluation: {args.url}")
    print(f"Tabs: {args.tab}, Viewports: {list(VIEWPORTS.keys())}")
    print("=" * 65)

    scores = evaluate_all(url=args.url, tabs=args.tab)
    print_summary(scores)
    save_scores(scores, label=args.label)
