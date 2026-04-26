# Quickstart: milai (v1 TUI)

**Branch**: `001-mvp-tui` | **Date**: 2026-04-26

---

## Prerequisites

- Python 3.12+
- `uv` (package manager)
- An API key for your chosen LLM provider (default: Google Gemini)

---

## Setup

```bash
# Clone / navigate to the repo
cd milai

# Install all dependencies
uv sync

# Set your LLM provider API key (secrets stay in env vars — never in config files)
export GEMINI_API_KEY="your-key-here"
```

To customise the model or generation parameters, edit (or create) `~/.milai/config.yaml`:

```yaml
llm:
  model: gemini/gemini-2.0-flash   # any LiteLLM-compatible model string
  temperature: 0.7
  top_p: 0.95
  max_tokens: 1024
```

All keys are optional — missing values fall back to the defaults shown above. To use a different provider:

```yaml
# OpenAI
llm:
  model: openai/gpt-4o-mini
# requires: export OPENAI_API_KEY="..."

# Anthropic
llm:
  model: anthropic/claude-haiku-4-5
# requires: export ANTHROPIC_API_KEY="..."
```

---

## Running

```bash
uv run milai
```

On first launch, milai runs the **onboarding** flow:
1. Asks for your target language
2. Asks optional preferences (goal, native language, study time)
3. Starts a 5–10 minute adaptive assessment
4. Generates a personalised curriculum for your review
5. Enters the learning loop

State is saved automatically to `~/.milai/state.json`. Close and reopen to resume exactly where you left off.

---

## Resetting Your Profile

```bash
uv run milai --reset
```

Deletes `~/.milai/state.json` and starts fresh. A backup prompt is shown before deletion.

---

## Running Tests

```bash
# All tests
uv run pytest

# Unit only
uv run pytest tests/unit/

# Contract tests (verify IOMediator / LLMClient / StorageClient implementations)
uv run pytest tests/contract/

# Full QA (format + lint + type-check + tests)
just qa
```

---

## Project Layout

See [plan.md](plan.md) for the full annotated project layout.

---

## Configuration

### `~/.milai/config.yaml` — LLM and app settings

| Key | Default | Description |
|---|---|---|
| `llm.model` | `gemini/gemini-2.0-flash` | Any LiteLLM-compatible model string |
| `llm.temperature` | `0.7` | Sampling temperature |
| `llm.top_p` | `0.95` | Nucleus sampling threshold |
| `llm.max_tokens` | `1024` | Max tokens per LLM response |
| `storage.path` | `~/.milai/state.json` | Override state file location |
| `storage.history_path` | `~/.milai/history.db` | Override SQLite history DB location |

### Environment variables — API keys only

| Variable | Required for |
|---|---|
| `GEMINI_API_KEY` | Default model (`gemini/gemini-2.0-flash`) |
| `OPENAI_API_KEY` | OpenAI models |
| `ANTHROPIC_API_KEY` | Anthropic models |

API keys are intentionally not in `config.yaml` — secrets must not be written to files.
