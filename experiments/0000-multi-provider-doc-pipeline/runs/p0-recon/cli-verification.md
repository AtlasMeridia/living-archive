# CLI Structured Output Verification

**Date**: 2026-02-18

## Smoke Test

All three providers were tested with the same trivial classification task:
- Input: `"Classify this document: 'Last Will and Testament of John Smith, dated March 2020'"`
- Schema: `{"document_type": string, "confidence": number}` (strict, no additional properties)

## Results

### Claude CLI — PASS

**Command**:
```bash
claude -p "PROMPT" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"document_type":{"type":"string"},"confidence":{"type":"number"}},"required":["document_type","confidence"],"additionalProperties":false}' \
  --model sonnet \
  --no-session-persistence
```

**Output format**: JSON envelope with `structured_output` field containing the schema-valid object.

```json
{"document_type": "Legal - Last Will and Testament", "confidence": 0.99}
```

**Parsing path**: `json.loads(stdout)["structured_output"]`

**Notes**:
- Returns a full envelope with `type`, `result` (text), `usage`, `structured_output`, etc.
- `structured_output` is guaranteed to match the provided schema
- Usage reported: input_tokens, output_tokens, cache stats
- Model used: `claude-sonnet-4-6`

### Codex CLI — PASS

**Command**:
```bash
codex exec "PROMPT" \
  --json \
  --output-schema /tmp/schema.json \
  -o /tmp/output.json \
  --skip-git-repo-check \
  --ephemeral
```

**Output format**: JSONL to stdout (streaming events), final output written to `-o` file.

```json
{"document_type": "Last Will and Testament", "confidence": 0.99}
```

**Parsing path**: `json.loads(Path(output_file).read_text())`

**Notes**:
- Schema must be written to a file (no inline schema flag)
- Stdout is JSONL with event types: `thread.started`, `turn.started`, `item.completed`, `turn.completed`
- The `-o` output file contains only the schema-valid JSON (clean, no envelope)
- Usage available in `turn.completed` event: `input_tokens`, `cached_input_tokens`, `output_tokens`

### Ollama (qwen3:32b) — PASS

**Command** (via OpenAI-compatible API):
```python
POST http://localhost:11434/v1/chat/completions
{
  "model": "qwen3:32b",
  "messages": [{"role": "user", "content": "PROMPT"}],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "doc_classification",
      "strict": true,
      "schema": { ... }
    }
  }
}
```

**Output format**: Standard OpenAI chat completion response.

```json
{"document_type": "last_will_and_testament", "confidence": 0.98}
```

**Parsing path**: `json.loads(response["choices"][0]["message"]["content"])`

**Notes**:
- Uses `json_schema` response format (not just `json_object`)
- Returns standard OpenAI-compatible usage: `prompt_tokens`, `completion_tokens`
- Lowercase/snake_case style in output (may need normalization for comparison)

## Invocation Contracts

| Aspect | Claude CLI | Codex CLI | Ollama |
|--------|-----------|-----------|--------|
| Schema delivery | Inline `--json-schema` | File `--output-schema FILE` | In request body |
| Output location | stdout JSON envelope | `-o FILE` | HTTP response body |
| Parse path | `stdout.structured_output` | `file contents` | `choices[0].message.content` |
| Usage tracking | `envelope.usage` | JSONL `turn.completed.usage` | `response.usage` |
| Session mgmt | `--no-session-persistence` | `--ephemeral` | stateless |
| Timeout control | process timeout | process timeout | HTTP timeout |

## Verdict

All three providers reliably produce schema-valid structured JSON output. No decision gate blockers.
