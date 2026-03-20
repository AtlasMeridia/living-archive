"""Analysis providers for Claude and GPT CLI tools.

Both implement the same Protocol so the runner can dispatch uniformly.
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
from .schemas import DocumentAnalysis, PhotoAnalysis, make_openai_strict

log = logging.getLogger("exp0004")


def _is_rate_limit(stderr: str) -> bool:
    lower = stderr.lower()
    return any(s in lower for s in config.RATE_LIMIT_SIGNALS)


class AnalysisProvider(Protocol):
    name: str

    def analyze_photo(
        self, jpeg_path: Path, folder_hint: str,
    ) -> tuple[dict, dict]: ...

    def analyze_document(
        self, text: str, source_file: str, page_count: int,
    ) -> tuple[dict, dict]: ...


# --- Claude CLI ---


class ClaudeProvider:
    name = "claude"

    def _photo_prompt(self, jpeg_path: Path, folder_hint: str) -> str:
        template = config.PHOTO_PROMPT_FILE.read_text()
        base = template.format(folder_hint=folder_hint)
        return f"Read and analyze the photo at: {jpeg_path.resolve()}\n\n{base}"

    def _doc_prompt(self, text: str, source_file: str, page_count: int) -> str:
        template = config.DOC_PROMPT_FILE.read_text()
        return template.format(
            source_file=source_file, page_count=page_count, text=text,
        )

    def _run_claude(self, prompt: str, schema: str, timeout: int,
                    allow_read: bool = False) -> dict:
        cmd = [
            str(config.CLAUDE_CLI), "-p", prompt,
            "--output-format", "json",
            "--json-schema", schema,
            "--model", config.CLAUDE_MODEL,
            "--no-session-persistence",
        ]
        if allow_read:
            cmd.extend(["--allowedTools", "Read"])

        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
        )
        if result.returncode != 0:
            msg = f"Claude CLI exited {result.returncode}: {result.stderr[:500]}"
            if result.stderr and _is_rate_limit(result.stderr):
                raise RateLimitError(msg)
            raise RuntimeError(msg)

        return json.loads(result.stdout)

    def _extract_meta(self, envelope: dict, prompt_version: str) -> dict:
        usage = envelope.get("usage", {})
        return {
            "provider": self.name,
            "model": envelope.get("model", config.CLAUDE_MODEL),
            "prompt_version": prompt_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    def analyze_photo(
        self, jpeg_path: Path, folder_hint: str,
    ) -> tuple[dict, dict]:
        prompt = self._photo_prompt(jpeg_path, folder_hint)
        schema = json.dumps(PhotoAnalysis.model_json_schema())
        envelope = self._run_claude(
            prompt, schema, config.PHOTO_TIMEOUT, allow_read=True,
        )
        analysis = envelope["structured_output"]
        PhotoAnalysis.model_validate(analysis)  # validate
        meta = self._extract_meta(envelope, config.PHOTO_PROMPT_VERSION)
        return analysis, meta

    def analyze_document(
        self, text: str, source_file: str, page_count: int,
    ) -> tuple[dict, dict]:
        prompt = self._doc_prompt(text, source_file, page_count)
        schema = json.dumps(make_openai_strict(
            DocumentAnalysis.model_json_schema()
        ))
        envelope = self._run_claude(prompt, schema, config.DOC_TIMEOUT)
        analysis = envelope["structured_output"]
        DocumentAnalysis.model_validate(analysis)
        meta = self._extract_meta(envelope, config.DOC_PROMPT_VERSION)
        return analysis, meta


# --- GPT (Codex CLI) ---


class GptProvider:
    name = "gpt"

    def _photo_prompt(self, folder_hint: str) -> str:
        template = config.PHOTO_PROMPT_FILE.read_text()
        return template.format(folder_hint=folder_hint)

    def _doc_prompt(self, text: str, source_file: str, page_count: int) -> str:
        template = config.DOC_PROMPT_FILE.read_text()
        return template.format(
            source_file=source_file, page_count=page_count, text=text,
        )

    def _run_codex(self, prompt: str, schema: dict, timeout: int,
                   image_path: Path | None = None) -> tuple[dict, dict]:
        schema_fd, schema_path = tempfile.mkstemp(
            suffix=".json", prefix="exp0004-schema-",
        )
        out_fd, out_path = tempfile.mkstemp(
            suffix=".json", prefix="exp0004-out-",
        )
        try:
            with open(schema_fd, "w") as f:
                json.dump(schema, f)
            os.close(out_fd)

            cmd = [
                str(config.CODEX_CLI), "exec", prompt,
                "-m", config.GPT_MODEL,
                "--json",
                "--output-schema", schema_path,
                "-o", out_path,
                "--skip-git-repo-check",
                "--ephemeral",
            ]
            if image_path:
                cmd.extend(["-i", str(image_path.resolve())])

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode != 0:
                msg = f"Codex CLI exited {result.returncode}: {result.stderr[:500]}"
                if result.stderr and _is_rate_limit(result.stderr):
                    raise RateLimitError(msg)
                raise RuntimeError(msg)

            raw = Path(out_path).read_text().strip()
            analysis = json.loads(raw)

            # Extract token usage from JSONL stdout
            usage = {}
            for line in result.stdout.strip().splitlines():
                try:
                    event = json.loads(line)
                    if event.get("type") == "turn.completed":
                        usage = event.get("usage", {})
                except json.JSONDecodeError:
                    continue

            return analysis, usage
        finally:
            Path(schema_path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)

    def _build_meta(self, usage: dict, prompt_version: str) -> dict:
        return {
            "provider": self.name,
            "model": config.GPT_MODEL,
            "prompt_version": prompt_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    def analyze_photo(
        self, jpeg_path: Path, folder_hint: str,
    ) -> tuple[dict, dict]:
        prompt = self._photo_prompt(folder_hint)
        schema = make_openai_strict(PhotoAnalysis.model_json_schema())
        analysis, usage = self._run_codex(
            prompt, schema, config.PHOTO_TIMEOUT, image_path=jpeg_path,
        )
        PhotoAnalysis.model_validate(analysis)
        meta = self._build_meta(usage, config.PHOTO_PROMPT_VERSION)
        return analysis, meta

    def analyze_document(
        self, text: str, source_file: str, page_count: int,
    ) -> tuple[dict, dict]:
        prompt = self._doc_prompt(text, source_file, page_count)
        schema = make_openai_strict(DocumentAnalysis.model_json_schema())
        analysis, usage = self._run_codex(prompt, schema, config.DOC_TIMEOUT)
        DocumentAnalysis.model_validate(analysis)
        meta = self._build_meta(usage, config.DOC_PROMPT_VERSION)
        return analysis, meta


# --- Shared ---


class RateLimitError(Exception):
    """CLI stderr indicates a rate limit / capacity issue."""


PROVIDERS: dict[str, type] = {
    "claude": ClaudeProvider,
    "gpt": GptProvider,
}


def get_provider(name: str) -> AnalysisProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}. Choose from: {list(PROVIDERS)}")
    return cls()
