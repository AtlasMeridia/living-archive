"""Document analysis via multi-provider LLM dispatch.

Providers: Claude CLI, Codex CLI, Ollama (OpenAI-compatible API).
Each takes pre-extracted text and returns structured DocumentAnalysis.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from . import config
from .config import CliRateLimitError
from .models import DocumentAnalysis, DocumentInferenceMetadata, Sensitivity

log = logging.getLogger("living_archive")

_RATE_LIMIT_SIGNALS = (
    "rate limit", "rate_limit", "429", "quota", "try again later",
    "overloaded", "capacity", "cooldown",
)


def _is_rate_limit_error(stderr: str) -> bool:
    """Check if CLI stderr indicates a rate limit / capacity issue."""
    lower = stderr.lower()
    return any(s in lower for s in _RATE_LIMIT_SIGNALS)


# --- Schema and prompt helpers ---


def _make_openai_strict(schema: dict) -> dict:
    """Recursively fix a Pydantic JSON Schema for OpenAI strict mode.

    OpenAI requires:
    - additionalProperties: false on all objects
    - required: [all property keys] on all objects
    - No 'default' values on properties
    """
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
        for prop in schema["properties"].values():
            prop.pop("default", None)
            _make_openai_strict(prop)
    if "items" in schema:
        _make_openai_strict(schema["items"])
    # Handle $defs (Pydantic puts nested models here)
    for defn in schema.get("$defs", {}).values():
        _make_openai_strict(defn)
    return schema


def _doc_analysis_schema() -> dict:
    """Generate JSON Schema from the DocumentAnalysis Pydantic model.

    Adds additionalProperties: false at all object levels for
    OpenAI/Codex strict mode compatibility.
    """
    schema = DocumentAnalysis.model_json_schema()
    return _make_openai_strict(schema)


def _build_prompt(source_file: str, page_count: int, text: str) -> str:
    """Format the document analysis prompt with extracted text."""
    template = config.DOC_PROMPT_FILE.read_text()
    return template.format(
        source_file=source_file,
        page_count=page_count,
        text=text,
    )


# --- Provider protocol ---


class AnalysisProvider(Protocol):
    """Interface for document analysis providers."""

    name: str

    def analyze(
        self,
        text: str,
        source_file: str,
        page_count: int,
    ) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]: ...


# --- Claude CLI provider ---


class ClaudeCliProvider:
    name = "claude-cli"

    def analyze(
        self,
        text: str,
        source_file: str,
        page_count: int,
    ) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
        prompt = _build_prompt(source_file, page_count, text)
        schema = json.dumps(_doc_analysis_schema())

        cmd = [
            str(config.CLAUDE_CLI),
            "-p", prompt,
            "--output-format", "json",
            "--json-schema", schema,
            "--model", config.DOC_CLI_MODEL,
            "--no-session-persistence",
        ]

        log.debug("Claude CLI: analyzing %s (%d pages)", source_file, page_count)
        # Unset CLAUDECODE to allow spawning from within a Claude session
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=config.DOC_TIMEOUT, env=env,
        )

        if result.returncode != 0:
            msg = (
                f"Claude CLI exited {result.returncode}: "
                f"{result.stderr[:500] if result.stderr else 'no stderr'}"
            )
            if result.stderr and _is_rate_limit_error(result.stderr):
                raise CliRateLimitError(msg)
            raise RuntimeError(msg)

        envelope = json.loads(result.stdout)
        analysis = DocumentAnalysis.model_validate(envelope["structured_output"])

        usage = envelope.get("usage", {})
        inference = DocumentInferenceMetadata(
            method="auto",
            provider=self.name,
            model=envelope.get("model", config.DOC_CLI_MODEL),
            prompt_version=config.DOC_PROMPT_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            estimated_input_tokens=len(text) // 4,
        )
        return analysis, inference


# --- Codex CLI provider ---


class CodexCliProvider:
    name = "codex"

    def analyze(
        self,
        text: str,
        source_file: str,
        page_count: int,
    ) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
        prompt = _build_prompt(source_file, page_count, text)
        schema = _doc_analysis_schema()

        # Codex requires schema in a file, not inline
        schema_fd, schema_path = tempfile.mkstemp(suffix=".json", prefix="codex-schema-")
        out_fd, out_path = tempfile.mkstemp(suffix=".json", prefix="codex-out-")
        try:
            with open(schema_fd, "w") as f:
                json.dump(schema, f)
            os.close(out_fd)

            cmd = [
                str(config.CODEX_CLI),
                "exec", prompt,
                "--json",
                "--output-schema", schema_path,
                "-o", out_path,
                "--skip-git-repo-check",
                "--ephemeral",
            ]
            if config.CODEX_MODEL:
                cmd.extend(["-m", config.CODEX_MODEL])

            log.debug("Codex CLI: analyzing %s (%d pages)", source_file, page_count)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=config.DOC_TIMEOUT,
            )

            if result.returncode != 0:
                msg = (
                    f"Codex CLI exited {result.returncode}: "
                    f"{result.stderr[:500] if result.stderr else 'no stderr'}"
                )
                if result.stderr and _is_rate_limit_error(result.stderr):
                    raise CliRateLimitError(msg)
                raise RuntimeError(msg)

            # Parse output file
            raw = Path(out_path).read_text().strip()
            parsed = json.loads(raw)
            analysis = DocumentAnalysis.model_validate(parsed)

            # Extract usage from JSONL stdout
            input_tokens = 0
            output_tokens = 0
            for line in result.stdout.strip().splitlines():
                try:
                    event = json.loads(line)
                    if event.get("type") == "turn.completed":
                        usage = event.get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)
                except json.JSONDecodeError:
                    continue

            inference = DocumentInferenceMetadata(
                method="auto",
                provider=self.name,
                model=config.CODEX_MODEL or "codex-default",
                prompt_version=config.DOC_PROMPT_VERSION,
                timestamp=datetime.now(timezone.utc).isoformat(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_input_tokens=len(text) // 4,
            )
            return analysis, inference

        finally:
            Path(schema_path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)


# --- Ollama provider ---


class OllamaProvider:
    name = "ollama"

    def analyze(
        self,
        text: str,
        source_file: str,
        page_count: int,
    ) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
        import urllib.request

        prompt = _build_prompt(source_file, page_count, text)
        schema = _doc_analysis_schema()

        payload = json.dumps({
            "model": config.OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "document_analysis",
                    "strict": True,
                    "schema": schema,
                },
            },
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{config.OLLAMA_URL}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        log.debug("Ollama: analyzing %s (%d pages)", source_file, page_count)
        resp = json.loads(
            urllib.request.urlopen(req, timeout=config.DOC_TIMEOUT).read()
        )

        content = resp["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        analysis = DocumentAnalysis.model_validate(parsed)

        usage = resp.get("usage", {})
        inference = DocumentInferenceMetadata(
            method="auto",
            provider=self.name,
            model=config.OLLAMA_MODEL,
            prompt_version=config.DOC_PROMPT_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            estimated_input_tokens=len(text) // 4,
        )
        return analysis, inference


# --- Provider factory ---


_PROVIDERS: dict[str, type] = {
    "claude-cli": ClaudeCliProvider,
    "codex": CodexCliProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str | None = None) -> AnalysisProvider:
    """Get a provider instance by name (defaults to config.DOC_PROVIDER)."""
    name = name or config.DOC_PROVIDER
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}. Choose from: {list(_PROVIDERS)}")
    return cls()


# --- Chunk aggregation ---


def merge_chunk_analyses(
    analyses: list[tuple[DocumentAnalysis, DocumentInferenceMetadata]],
) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
    """Merge analyses from multiple chunks of the same document.

    Strategy:
    - document_type, title, language, quality: from first chunk
    - date: highest confidence across chunks
    - summaries: concatenated
    - key_people, key_dates, tags: union (order-preserving)
    - sensitivity: OR across all chunks (conservative — any True wins)
    - tokens: summed
    """
    if len(analyses) == 1:
        return analyses[0]

    first_analysis = analyses[0][0]
    first_inference = analyses[0][1]

    # Find highest-confidence date
    best_date = first_analysis.date
    best_date_conf = first_analysis.date_confidence
    for a, _ in analyses[1:]:
        if a.date_confidence > best_date_conf:
            best_date = a.date
            best_date_conf = a.date_confidence

    # Union sets (order-preserving)
    def _union_lists(*lists: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for lst in lists:
            for item in lst:
                if item not in seen:
                    seen.add(item)
                    result.append(item)
        return result

    all_people = _union_lists(*(a.key_people for a, _ in analyses))
    all_dates = _union_lists(*(a.key_dates for a, _ in analyses))
    all_tags = _union_lists(*(a.tags for a, _ in analyses))

    # OR sensitivity flags
    merged_sensitivity = Sensitivity(
        has_ssn=any(a.sensitivity.has_ssn for a, _ in analyses),
        has_financial=any(a.sensitivity.has_financial for a, _ in analyses),
        has_medical=any(a.sensitivity.has_medical for a, _ in analyses),
    )

    # Concatenate summaries
    en_parts = [a.summary_en for a, _ in analyses if a.summary_en]
    zh_parts = [a.summary_zh for a, _ in analyses if a.summary_zh]

    merged_analysis = DocumentAnalysis(
        document_type=first_analysis.document_type,
        title=first_analysis.title,
        date=best_date,
        date_confidence=best_date_conf,
        summary_en=" ".join(en_parts),
        summary_zh="".join(zh_parts),
        key_people=all_people,
        key_dates=all_dates,
        sensitivity=merged_sensitivity,
        tags=all_tags,
        language=first_analysis.language,
        quality=first_analysis.quality,
    )

    # Sum tokens across chunks
    total_input = sum(inf.input_tokens for _, inf in analyses)
    total_output = sum(inf.output_tokens for _, inf in analyses)

    merged_inference = DocumentInferenceMetadata(
        method=first_inference.method,
        provider=first_inference.provider,
        model=first_inference.model,
        prompt_version=first_inference.prompt_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_tokens=total_input,
        output_tokens=total_output,
        chunk_count=len(analyses),
    )

    return merged_analysis, merged_inference


# --- Main entry point ---


@config.retry()
def analyze_document(
    text: str,
    source_file: str,
    page_count: int,
    provider_name: str | None = None,
) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
    """Analyze a document using the configured provider.

    This is the main entry point — wraps provider.analyze() with retry logic.
    """
    provider = get_provider(provider_name)
    return provider.analyze(text, source_file, page_count)
