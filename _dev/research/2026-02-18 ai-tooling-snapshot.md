# AI Tooling Snapshot — Document the Present

## Why this matters

The Living Archive is being built during a specific moment in AI development. The tools, workflows, and limitations we work with today will look different in weeks or months. That transience is itself worth capturing.

Posts, blog entries, and documentation produced by this project should note the current AI tooling practices as they're being used — not as an aside, but as a first-class part of the narrative. This serves two audiences:

1. **People learning AI tooling now.** Most guides assume familiarity. Showing the actual workflow — Claude Code sessions, CLI subprocess dispatch, structured output schemas, token budget management, retry logic around rate limits — gives a concrete starting point for people who haven't built with these tools yet.

2. **Future readers (including us).** The practices that feel like hard-won knowledge today — batching around subscription limits, estimating tokens from character counts, detecting rate limits from stderr strings — will likely be obsolete or built-in soon. Recording them timestamps where the tooling was and how fast it moved.

## What to capture

When writing about the project (blog posts, research notes, session logs):

- Name the specific models and tools being used (Claude Sonnet, Claude Code CLI, Codex CLI, Ollama + Qwen3)
- Describe the actual workflow, not an idealized version — including the friction points
- Note what's manual that should be automated, and what's automated that used to be manual
- When a workaround exists because the tooling doesn't support something natively, say so
- Include token counts, timing, and cost observations — these are the kind of details that become interesting historical data

## Current state (February 2026)

- **Primary tool:** Claude Code CLI (`claude -p`) as a subprocess, invoked per-document with `--output-format json --json-schema`
- **Structured output:** Works reliably but requires passing full JSON Schema on every call; no session persistence between documents
- **Rate limits:** Subscription-tier (Max plan), managed by batch sizing and pacing delays rather than API-level headers; rate limit detection is string-matching on stderr
- **Token accounting:** CLI reports usage in an envelope, but input_tokens is unreliable (reports 3 for multi-thousand-token inputs); we estimate from character count as a workaround
- **Local inference:** Ollama with Qwen3:32b as a fallback/alternative, accessed via OpenAI-compatible API
- **Multi-provider:** Pipeline supports swapping providers via env var, but each has different quirks (CLI flags, output formats, schema handling)

These details will shift. That's the point of writing them down.
