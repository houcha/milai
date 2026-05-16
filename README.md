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
      model: gemini/gemma-4-31b-it
      temperature: 0.7
      top_p: 0.95
      max_tokens: 1024
states: {}
```

API keys stay in environment variables and should not be written into config
files.

## Usage

Run the TUI entrypoint:

```bash
uv run milai
```

The application stores local progress in `~/.milai/state.json` and resumes the
active session on launch.

## QA

Use the project commands from the shared toolchain:

```bash
just qa
just type-check-concise
uv run pytest
prek run
```
