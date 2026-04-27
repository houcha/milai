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
  default_profile: light
  profiles:
    light:
      model: gemini/gemini-2.0-flash   # any LiteLLM-compatible model string
      temperature: 0.7
      top_p: 0.95
      max_tokens: 1024
states: {}
```

All keys are optional — missing values fall back to the defaults shown above. To use a different provider:

```yaml
# OpenAI
llm:
  profiles:
    light:
      model: openai/gpt-4o-mini
# requires: export OPENAI_API_KEY="..."

# Anthropic
llm:
  profiles:
    light:
      model: anthropic/claude-haiku-4-5
# requires: export ANTHROPIC_API_KEY="..."
```

You can also route specific app states to a different model. This is useful when keeping structured lesson generation on a cheap multilingual model while using a stronger conversational model for open-ended learner questions:

```yaml
llm:
  default_profile: light
  profiles:
    light:
      model: gemini/gemini-2.0-flash
      temperature: 0.7
      top_p: 0.95
      max_tokens: 1024
    heavy:
      model: openai/gpt-4o-mini
      temperature: 0.8
      top_p: 0.95
      max_tokens: 1536

states:
  deviation:
    llm: heavy
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
| `llm.default_profile` | `light` | Fallback LLM profile for states without an override |
| `llm.profiles.<profile>.model` | `gemini/gemini-2.0-flash` for `light` | Any LiteLLM-compatible model string |
| `llm.profiles.<profile>.temperature` | `0.7` for `light` | Sampling temperature |
| `llm.profiles.<profile>.top_p` | `0.95` for `light` | Nucleus sampling threshold |
| `llm.profiles.<profile>.max_tokens` | `1024` for `light` | Max tokens per LLM response |
| `states.<state>.llm` | unset | Optional LLM profile name for a state such as `deviation` |
| `storage.path` | `~/.milai/state.json` | Override state file location |

### Environment variables — API keys only

| Variable | Required for |
|---|---|
| `GEMINI_API_KEY` | Default `light` profile (`gemini/gemini-2.0-flash`) |
| `OPENAI_API_KEY` | OpenAI models |
| `ANTHROPIC_API_KEY` | Anthropic models |

API keys are intentionally not in `config.yaml` — secrets must not be written to files.
