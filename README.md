# milai

A conversational language tutor with durable learning evidence. Local text chat,
complete stored lessons, OpenAI Agents SDK, and Langfuse tracing.

## Run

Install Python 3.12+ and uv, then `uv sync`. Put credentials in `.env` using
[.env.example](.env.example) as a guide. Main chat, lesson discussion, assessment,
and additional practice use `OPENAI_MODEL` (default `gpt-6.1-sol`) with low reasoning.
Complete lessons and reviews use `OPENAI_LESSON_MODEL` (default `gpt-6.1-sol`) with
`low` reasoning, requested Fast processing, and a 32,768-token output budget.
The models share one authenticated Responses API client. `OPENAI_API_KEY` is
required; requests are billed to its project. There are no automatic retries or
provider/model fallbacks; old Gemini variables are ignored. Langfuse records
usage, not a billing guarantee.

```sh
uv run milai probe
uv run milai chat
uv run milai chat --session SESSION_ID
uv run milai web
uv run milai inspect
uv run milai reset --yes
```

The web interface runs locally at `http://127.0.0.1:8765`. Use the **Sessions**
link to create or select a session; Rename and Delete appear beside each
session in that view. Selecting a session returns to its conversation.

The left sidebar shows generated lessons in chronological order, with the current
teaching focus highlighted. Clicking an older lesson opens its stored document and
persistent discussion without changing that focus. The lesson page shows the
explanation beside the discussion on desktop, or **Lesson** and **Discussion** tabs
on narrow screens. Exercises appear below the explanation with answer fields and
question actions. **Back to conversation** returns to main chat; **Continue learning**
carries the lesson context into a new main-chat request. **Skills** shows observation
counts and derived mastery. Each session owns its main conversation, lessons,
discussions, skills, and practice evidence.

The web UI replays the latest non-empty session on load. Use `--session SESSION_ID`
to open a particular session or `--port PORT` to select another local port.
It binds only to the loopback interface. Tutor replies use a locally bundled
Markdown-It and KaTeX renderer, including math notation. The checked-in bundle
works without Node.js at runtime; after editing `markdown-renderer.js`, rebuild it
with `npm ci && npm run build:web` and run `npm run test:web`.
Inside terminal chat, `/lessons` lists stored lessons, `/lesson <id>` opens one,
`/back` returns to main chat, and `/answer <exercise-id> <text>` submits its
exercise. `/state` shows learning memory, `/new` starts a fresh session, and
`/quit` exits. The session ID is printed at startup.

SQLite data lives in `.milai/learning.sqlite3` (override `MILAI_DATABASE`).
Schema 5 stores fixed lesson documents, scoped turns, discussion summaries, and
current teaching focus. Older databases require `milai reset --yes`, which archives
the database and sidecars before creating a fresh one. Protect these files
as personal data. This is a local app; there is no shared service or login.

Main chat discovers intent and generates a complete lesson on one precise language
skill, with an **Open lesson** card. Each lesson contains its explanation, worked
examples, recap, prepared exercises, and ongoing discussion. New skills require
all prerequisite skills to be mastered. Mastery is derived from two independent
successes on distinct exercises since the last substantial difficulty observation;
no numeric score is assigned. A minor slip leaves prepared practice available
while deferring a new remedial drill. Earlier skills may support a new lesson's
exercises. Assessments can recommend a due review; an explicit continuation request
lets main chat choose an eligible next lesson or review. The tutor records
skill-specific help and evidence. It can also
retrieve learner-supplied public HTTPS text/HTML or retain pasted excerpts.
Unsupported sources fail honestly. No web search, PDF, audio, video, authenticated
pages, or redirect following is implemented yet.

## Tracing and validation

Set all three Langfuse variables in `.env` and ensure that endpoint is running.
The supported OpenInference Agents integration captures framework spans; application
spans include committed learning-event IDs and the prompt hash. Content is hidden
by default. Set `MILAI_TRACE_CONTENT=true` only for synthetic or consented transcripts.
Learning evidence remains in local SQLite even when tracing is unavailable.
Responses are sent with `store=false`; conversation state stays in local SQLite.

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
The [validation results](docs/validation.md) record a live model probe, synthetic
acceptance run, deterministic checks, and layout screenshots. The separate
[teaching review](docs/teaching-review.md) describes the quality limitation found
in the live generated lesson; passing application contracts is not a general
teaching-quality claim.
