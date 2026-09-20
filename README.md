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
uses Low reasoning effort; a required private topic-decomposition pass uses High once
for each new topic.

```sh
uv run milai probe
uv run milai chat
uv run milai chat --session SESSION_ID
uv run milai web
uv run milai inspect
uv run milai reset --yes
```

The web interface runs locally at `http://127.0.0.1:8765`. It combines chat with a
learner profile and current focus beside chat. Open the breadcrumb menu next to
Milai to switch between Conversation, Learning Map, and Skills. Theory and exercises
appear as exact persisted cards in the conversation. Each view has its own
link and supports browser back/forward navigation. Use `--session SESSION_ID` to resume a conversation or
`--port PORT` to select another local port. It binds only to the loopback interface.

Inside chat, `/state` shows learning memory, `/new` starts a conversation while
retaining evidence, and `/quit` exits. The session ID is printed at startup.
SQLite data lives in `.milai/learning.sqlite3` (override `MILAI_DATABASE`). Schema 2
does not silently convert the earlier prototype database: startup explains how to run
`milai reset --yes`, which archives the database and sidecars before creating a fresh
one. Protect these files as personal data. This is a local app; there is no shared
service or login.

The tutor discovers intent through conversation, creates a reusable graph of precise
language skills, and links topics to those skills as application contexts. A learner-wide
focus tracks the current topic and 1–3 target skills. It can present structured theory,
create multi-skill exercises, give skill-specific help, assess actual attempts, and
expand or revise the graph as evidence grows. Progress is summarized from observations;
there is no mastery score. It can also retrieve learner-supplied public HTTPS text/HTML
or retain pasted excerpts. Unsupported sources fail honestly. No web search, PDF,
audio, video, authenticated pages, or redirect following is implemented yet.

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
The archived live Gemini report validates the previous schema and prompt. The current
skill-graph design has deterministic coverage and still needs a new live pedagogical
run. See [validation results](docs/validation.md) and the separate historical
[teaching-quality review](docs/teaching-review.md).
