# milai

AI-native, self-paced language learning in a terminal UI.

## Setup

Install the project and development dependencies with `uv`:

```bash
uv sync
```

Set an API key for the LLM provider selected in your config. The default
profile uses Gemini through LiteLLM:

```bash
export GEMINI_API_KEY="your-key-here"
```

## Configuration

Runtime config lives at `~/.milai/config.yaml`. If the file is missing, milai
uses the default `light` LLM profile:

```yaml
llm:
  default_profile: light
  profiles:
    light:
      model: gemini/gemini-3.1-flash-lite
states: {}
```

Generation parameters such as `temperature`, `top_p`, `max_tokens`, and
`reasoning_effort` are passed through to LiteLLM only when explicitly set. When
omitted, provider/model defaults are used.

State-specific model routing can be configured under `states.<state>.llm` with
one of the named profiles from `llm.profiles`.

API keys stay in environment variables and should not be written into config
files.

## Usage

Run the TUI entrypoint:

```bash
uv run milai
```

The application stores local progress in `~/.milai/state.json`. On launch, a
saved session can be continued or replaced with a new onboarding flow.

To delete the saved session before launch, run:

```bash
uv run milai --reset
```

The reset path asks for confirmation before deleting local state. If the saved
state file cannot be read, milai reports the corrupt session and asks whether to
delete it and start fresh.

## QA

Use the project commands from the shared toolchain:

```bash
just qa
just type-check-concise
uv run pytest tests/unit
uv run pytest tests/contract
uv run pytest tests/integration
prek run
```
