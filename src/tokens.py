"""Generate CSS custom properties from atlas-style-guide tokens.json.

Reads the canonical design tokens from the atlas-style-guide project and
produces a CSS string with :root variables, theme blocks, and a Google
Fonts @import. This keeps living-archive in sync with the style guide
without hardcoding values.
"""

import json
from pathlib import Path

from . import config


def _load_tokens() -> dict:
    """Load tokens.json from the atlas-style-guide project."""
    path = config.STYLE_GUIDE_ROOT / "data" / "tokens.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Style guide tokens not found: {path}\n"
            f"Set STYLE_GUIDE_ROOT to point to the atlas-style-guide project."
        )
    return json.loads(path.read_text())


def _google_fonts_url(tokens: dict) -> str:
    """Build a Google Fonts @import URL from font definitions."""
    fonts = tokens["typography"]["fonts"]
    families = []
    for font in fonts.values():
        if gf := font.get("googleFonts"):
            families.append(gf)
    params = "&".join(f"family={f}" for f in families)
    return f"https://fonts.googleapis.com/css2?{params}&display=swap"


def generate_css() -> str:
    """Generate full CSS from tokens.json."""
    tokens = _load_tokens()
    lines: list[str] = []

    # Google Fonts import
    lines.append(f'@import url("{_google_fonts_url(tokens)}");')
    lines.append("")

    version = tokens["meta"]["version"]
    lines.append(f"/* ATLAS Meridia Design Tokens v{version} */")
    lines.append(f"/* Generated from atlas-style-guide/data/tokens.json */")
    lines.append("")

    # :root — base tokens
    lines.append(":root {")

    # Colors: navy scale
    for key, color in tokens["colors"]["navy"].items():
        lines.append(f"  --navy-{key}: {color['value']};")
    lines.append("")

    # Colors: cream scale
    for key, color in tokens["colors"]["cream"].items():
        lines.append(f"  --cream-{key}: {color['value']};")
    lines.append("")

    # Colors: accent
    lines.append(f"  --accent-light: {tokens['colors']['accent']['light']['value']};")
    lines.append(f"  --accent: {tokens['colors']['accent']['default']['value']};")
    lines.append(f"  --accent-dark: {tokens['colors']['accent']['dark']['value']};")
    lines.append(f"  --accent-deep: {tokens['colors']['accent']['deep']['value']};")
    lines.append("")

    # Colors: semantic
    lines.append(f"  --success: {tokens['colors']['semantic']['success']['value']};")
    lines.append(f"  --error: {tokens['colors']['semantic']['error']['value']};")
    lines.append("  --warning: var(--accent);")
    lines.append("")

    # Typography: font families
    fonts = tokens["typography"]["fonts"]
    lines.append(f"  --font-display: {fonts['display']['family']};")
    lines.append(f"  --font-body: {fonts['body']['family']};")
    lines.append(f"  --font-ui: {fonts['ui']['family']};")
    lines.append(f"  --font-mono: {fonts['mono']['family']};")
    lines.append(f"  --font-chinese: {fonts['chinese']['family']};")
    lines.append("")

    # Typography: scale
    for key, size in tokens["typography"]["scale"].items():
        lines.append(f"  --text-{key}: {size['value']};")
    lines.append("")

    # Typography: line height
    for key, lh in tokens["typography"]["lineHeight"].items():
        lines.append(f"  --leading-{key}: {lh['value']};")
    lines.append("")

    # Typography: letter spacing
    for key, ls in tokens["typography"]["letterSpacing"].items():
        lines.append(f"  --tracking-{key}: {ls['value']};")
    lines.append("")

    # Spacing
    for key, space in tokens["spacing"].items():
        lines.append(f"  --space-{key}: {space['value']};")
    lines.append("")

    # Layout
    for key, width in tokens["layout"].items():
        lines.append(f"  --width-{key}: {width['value']};")
    lines.append("")

    # Motion
    lines.append(f"  --transition-fast: {tokens['motion']['fast']['value']};")
    lines.append(f"  --transition-base: {tokens['motion']['base']['value']};")
    lines.append(f"  --transition-slow: {tokens['motion']['slow']['value']};")
    lines.append(f"  --ease-out-expo: {tokens['motion']['easeOutExpo']['value']};")
    lines.append("")

    # Effects
    for key, radius in tokens["effects"]["borderRadius"].items():
        css_key = "border-radius" if key == "default" else f"border-radius-{key}"
        lines.append(f"  --{css_key}: {radius['value']};")
    lines.append("")
    for key, shadow in tokens["effects"]["shadow"].items():
        css_key = "shadow" if key == "default" else f"shadow-{key}"
        lines.append(f"  --{css_key}: {shadow['value']};")

    lines.append("}")
    lines.append("")

    # Light mode theme
    lines.append(":root, [data-theme='light'] {")
    light = tokens["themes"]["light"]
    lines.append(f"  --bg-primary: {light['bgPrimary']};")
    lines.append(f"  --bg-deep: {light['bgDeep']};")
    lines.append(f"  --bg-elevated: {light['bgElevated']};")
    lines.append(f"  --text-primary: {light['textPrimary']};")
    lines.append(f"  --text-secondary: {light['textSecondary']};")
    lines.append(f"  --text-muted: {light['textMuted']};")
    lines.append(f"  --border-color: {light['borderColor']};")
    lines.append(f"  --body-weight: {light['bodyWeight']};")
    lines.append(f"  --body-tracking: {light['bodyTracking']};")
    lines.append(f"  --accent-text: {light['accentText']};")
    lines.append("}")
    lines.append("")

    # Dark mode theme
    lines.append("[data-theme='dark'] {")
    dark = tokens["themes"]["dark"]
    lines.append(f"  --bg-primary: {dark['bgPrimary']};")
    lines.append(f"  --bg-deep: {dark['bgDeep']};")
    lines.append(f"  --bg-elevated: {dark['bgElevated']};")
    lines.append(f"  --text-primary: {dark['textPrimary']};")
    lines.append(f"  --text-secondary: {dark['textSecondary']};")
    lines.append(f"  --text-muted: {dark['textMuted']};")
    lines.append(f"  --border-color: {dark['borderColor']};")
    lines.append(f"  --body-weight: {dark['bodyWeight']};")
    lines.append(f"  --body-tracking: {dark['bodyTracking']};")
    lines.append(f"  --accent-text: {dark['accentText']};")
    lines.append("}")
    lines.append("")

    # System preference fallback
    lines.append("@media (prefers-color-scheme: dark) {")
    lines.append("  :root:not([data-theme='light']) {")
    lines.append(f"    --bg-primary: {dark['bgPrimary']};")
    lines.append(f"    --bg-deep: {dark['bgDeep']};")
    lines.append(f"    --bg-elevated: {dark['bgElevated']};")
    lines.append(f"    --text-primary: {dark['textPrimary']};")
    lines.append(f"    --text-secondary: {dark['textSecondary']};")
    lines.append(f"    --text-muted: {dark['textMuted']};")
    lines.append(f"    --border-color: {dark['borderColor']};")
    lines.append(f"    --body-weight: {dark['bodyWeight']};")
    lines.append(f"    --body-tracking: {dark['bodyTracking']};")
    lines.append(f"    --accent-text: {dark['accentText']};")
    lines.append("  }")
    lines.append("}")

    return "\n".join(lines)
