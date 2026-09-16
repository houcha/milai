# milai

A conversational language tutor with durable learning evidence. Local text chat,
OpenAI Agents SDK, Gemini 3.5 Flash Lite, and Langfuse tracing.

## Run

Install Python 3.12+ and uv, then `uv sync`. Put credentials in `.env` using
[.env.example](.env.example) as a guide. The default model is `gemini-3.5-flash-lite`
at Google's OpenAI-compatible endpoint. `GEMINI_API_KEY` is required. For no-spend
testing, use an AI Studio Free Tier project without billing attached. There are no
automatic retries or provider/model fallbacks; old NVIDIA variables are ignored.
Langfuse records usage, not a billing guarantee. Conversation
uses Low reasoning effort; optional deliberate planning uses High.

```sh
uv run milai probe
uv run milai chat
uv run milai chat --session SESSION_ID
uv run milai inspect
```

Inside chat, `/state` shows learning memory, `/new` starts a conversation while
retaining evidence, and `/quit` exits. The session ID is printed at startup.
SQLite data lives in `.milai/learning.sqlite3` (override `MILAI_DATABASE`). Protect
this file as personal data. This is a local app; there is no shared service or login.

The tutor discovers preferences through conversation. It can retrieve learner-supplied public HTTPS
text/HTML URLs or retain pasted excerpts, create exercises, give help, assess actual
attempts and adapt future teaching. It keeps source references and separates assisted
success from independent success. Unsupported sources fail honestly. No web search,
PDF, audio, video, authenticated pages or redirect following is implemented yet.

## Tracing and validation

Set all three Langfuse variables in `.env` and ensure that endpoint is running.
The supported OpenInference Agents integration captures framework spans; application
spans include committed learning-event IDs and the prompt hash. Content is hidden
by default. Set `MILAI_TRACE_CONTENT=true` only for synthetic or consented transcripts.
Learning evidence remains in local SQLite even when tracing is unavailable.

```sh
uv run pytest
uv run ruff check .
uv run ty check .
uv run python -m milai.acceptance
```

Tests mock model and retrieval responses. The probe and acceptance scenario use live
services. [Evaluation](docs/evaluation.md) explains the separate teaching-quality
review. [Product brief](docs/product.md), [architecture](docs/architecture.md), and
[decisions](docs/decisions.md) document scope, milestones and open product decisions.
The full live Gemini learning scenario passed all seven structural checks, including
assisted-success evidence and an adapted action after restart. See
[validation results](docs/validation.md) and the separate
[teaching-quality review](docs/teaching-review.md): prompt reliability, natural
examples, and precise assistance labels still need broader testing.
