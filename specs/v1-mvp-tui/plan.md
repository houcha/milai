# Implementation Plan: AI-Native Self-Paced Language Learning (milai)

**Branch**: `v1-mvp-tui` | **Date**: 2026-04-24 | **Spec**: [spec.md](spec.md)

---

## Summary

Build `milai`: a TUI-based, AI-native language learning application driven by a state machine that wraps an LLM. All user-facing I/O is mediated through an `IOMediator` protocol (Textual in v1; FastAPI in v2). All LLM calls go through an `LLMClient` protocol (LiteLLM-backed). A single `UserState` document is the canonical source of truth, persisted atomically to `~/.milai/state.json` after every transition. A lightweight SRS scheduler reinforces weak skill topics by injecting them into LLM prompts at lesson-generation time.

---

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: `textual>=8.2.4` (TUI), `litellm` (provider-agnostic LLM), `pydantic` (data model + structured LLM output), `pyyaml` (config file parsing)
**Storage**: Local JSON file at `~/.milai/state.json`; atomic writes via `tempfile` + `os.replace`
**Testing**: `pytest` (test runner), `ty` (type checker), `ruff` (lint + format)
**Target Platform**: Linux/macOS terminal (TUI); Docker + FastAPI in v2
**Project Type**: CLI/TUI application
**Performance Goals**: LLM response within user tolerance for conversational TUI (no hard latency SLA in v1); SRS scoring and state transitions are sub-millisecond
**Constraints**: Single-user per installation; no external service dependencies beyond an LLM provider API; state file must survive crashes (atomic writes)
**Scale/Scope**: Single learner; curriculum of 3–20 modules; skills list grows to ~100 topics over time; total state file size <1 MB

---

## Constitution Check

*Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Test-First | **Required** — all implementation tasks start with a failing test | RED → GREEN → REFACTOR; exploratory work (prompt tuning) must be scoped as a spike with coverage before merge |
| II. Evidence-Based Validation | **Required** — each state handler tested with real LLM call or realistic mock output | Bugs must reproduce in a failing test before fix is written |
| III. DRY | **Watch** — prompt-building patterns likely to repeat across states | Extract shared prompt-building utilities once pattern appears in 3+ handlers; not before |
| IV. YAGNI | **Gate passed** — no libraries added beyond what the current spec requires | `instructor` deferred until parse reliability is a demonstrated problem; sub-agents deferred; no SQLite |
| V. Provider Interface | **Gate passed** — `IOMediator`, `LLMClient`, `StorageClient` all defined as Protocols before any feature code | Concrete implementations injected at `main.py`; no state handler imports `litellm`, `textual`, or `pathlib` directly |

No violations. No Complexity Tracking entries required.

---

## Project Structure

### Documentation (this feature)

```
specs/v1-mvp-tui/
├── plan.md              # This file
├── research.md          # Phase 0: model selection, architecture decisions
├── data-model.md        # Phase 1: UserState document model + state transitions
├── quickstart.md        # Phase 1: setup, run, test, extend to v2
├── contracts/
│   ├── io_mediator.md   # IOMediator Protocol + ScriptedMediator test double
│   ├── llm_client.md    # LLMClient Protocol + ScriptedLLMClient test double
│   └── storage_client.md # StorageClient Protocol + InMemoryStorage test double
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```
milai/
├── __init__.py
├── main.py                      # entrypoint: loads config, resolves API keys from env, wires dependencies, runs machine
├── config.py                    # Config + LLMConfig dataclasses; loads ~/.milai/config.yaml with defaults
│
├── state/
│   ├── __init__.py
│   ├── machine.py               # run() loop: match/case dispatch → call handler → save state
│   ├── variants.py              # AppState discriminated union (Pydantic); all state variant models
│   ├── context.py               # SessionContext (in-memory only; session_id + pending_retry)
│   └── handlers/
│       ├── __init__.py
│       ├── onboarding.py        # async def step(state: OnboardingState, ...) -> tuple[AppState, UserState]
│       ├── assessment.py
│       ├── assessment_review.py
│       ├── curriculum_gen.py
│       ├── curriculum_review.py
│       ├── lesson.py
│       ├── deviation.py
│       ├── lesson_complete.py
│       └── curriculum_complete.py
│
├── models/
│   ├── __init__.py
│   ├── user_state.py            # UserState, UserProfile, Skill (Pydantic)
│   ├── curriculum.py            # Curriculum, Module, Lesson, Exercise (Pydantic)
│   ├── assessment.py            # AssessmentQuestion (Pydantic; used by AssessmentState variant)
│   └── history.py               # HistoryEvent union + all event payload types (Pydantic)
│
├── io/
│   ├── __init__.py
│   ├── mediator.py              # IOMediator Protocol; RichContent, Choice, ContentKind types
│   └── tui/
│       ├── __init__.py
│       └── app.py               # TextualMediator: Textual implementation of IOMediator
│
├── llm/
│   ├── __init__.py
│   ├── client.py                # LLMClient Protocol; Message, Role types
│   ├── litellm_client.py        # LiteLLMClient: wraps litellm.acompletion
│   ├── errors.py                # LLMError, LLMParseError
│   └── prompts/
│       ├── __init__.py
│       ├── assessment.py        # build_assessment_prompt() → list[Message]
│       ├── curriculum.py        # build_curriculum_prompt() → list[Message]
│       ├── lesson.py            # build_lesson_prompt() → list[Message]
│       └── feedback.py          # build_feedback_prompt() → list[Message]
│
├── storage/
│   ├── __init__.py
│   ├── client.py                # StorageClient + HistoryClient Protocols
│   ├── local.py                 # LocalStorage (state.json) + LocalHistory (history.db SQLite)
│   └── errors.py                # StorageError
│
└── srs/
    ├── __init__.py
    └── scheduler.py             # update_skill(), due_skills(), top_review_skills()

tests/
├── fakes/
│   ├── __init__.py
│   ├── mediator.py              # ScriptedMediator
│   ├── llm_client.py            # ScriptedLLMClient
│   └── storage_client.py        # InMemoryStorage + InMemoryHistory
├── unit/
│   ├── test_srs.py              # SRS rules: success/failure update, priority scoring, due detection
│   ├── test_state_machine.py    # match/case dispatch, transitions, resume from each state, LLMError retry
│   └── test_models.py           # UserState + AppState round-trip serialisation, discriminated union validation
├── integration/
│   ├── test_storage.py          # LocalStorage: atomic write, corruption detection, delete
│   └── test_llm_client.py       # LiteLLMClient: real or vcr-cassette endpoint
└── contract/
    ├── test_io_mediator.py      # assert TextualMediator satisfies IOMediator Protocol
    ├── test_llm_contract.py     # assert LiteLLMClient satisfies LLMClient Protocol
    └── test_storage_contract.py # assert LocalStorage satisfies StorageClient Protocol
```

**Structure Decision**: Single-project layout (Option 1). `milai/` is the source package; `tests/` mirrors its structure. The `io/tui/` subdirectory isolates Textual; `io/api/` (v2) will live alongside it without touching any other package. Three-tier test organisation: unit (fast, no I/O), integration (file system + optional real LLM), contract (Protocol conformance).

---

## Complexity Tracking

No violations to justify.

---

## Design Decisions Summary

Full rationale in [research.md](research.md). Key decisions:

| Decision | Choice | Key reason |
|---|---|---|
| Default LLM model | `gemini/gemini-2.0-flash` | Best multilingual coverage; Flash tier optimised for efficiency, not complex reasoning; most competitive cost |
| LLM configurability | `~/.milai/config.yaml` for model/temperature/top_p/max_tokens; env vars for API keys only | Multiple parameters are unwieldy as env vars; secrets must not be in files |
| Workflow architecture | Hand-rolled state machine; `AppState` discriminated union; `match/case` dispatch; `UserState`/`AppState` serialised separately | Clean domain/workflow separation; no impossible states; resume trivial; `match/case` is the full topology in ~20 lines — no abstractions needed at 9 states |
| Persistence format | JSON at `~/.milai/state.json` | Single-user, tiny dataset; human-readable; no migration complexity; atomic via `os.replace` |
| Spaced repetition | Custom lightweight (SM-2-inspired) | Topic-level granularity; feeds LLM prompts rather than driving a separate review session |
| Context management | Stateless per call; deviation capped at 10 exchanges | Predictable token budget; no cross-state history accumulation |
| Sub-agents | None in v1 | All LLM calls are single-turn; curriculum generated in one structured call for coherence |
| Structured LLM output | LiteLLM JSON mode + Pydantic | Provider-agnostic; type-safe; `instructor` available as drop-in if needed |

---

## Deferred

See [future.md](future.md) for full details. Summary:

- `ApiMediator` (FastAPI + WebSocket/SSE) and Docker packaging — v2
- LLM telemetry via Langfuse — v2/v3
- Multi-user support (auth, per-user state files, networked DB) — v2
- Sub-agent parallelism for large curriculum generation — v2+ if needed
- `instructor` adoption if LiteLLM JSON mode proves unreliable in practice
