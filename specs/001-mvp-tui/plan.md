# Implementation Plan: AI-Native Self-Paced Language Learning (milai)

**Branch**: `001-mvp-tui` | **Date**: 2026-04-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-mvp-tui/spec.md`

## Summary

Build `milai`: a TUI-based, AI-native language learning application driven by a state machine that wraps an LLM. The TUI is temporary scaffolding for v1; all user-facing I/O is mediated through an `IOMediator` protocol so the learning flow can later run behind the v2 browser interface without importing web framework or browser transport details. All LLM calls go through an `LLMClient` protocol (LiteLLM-backed). State-specific prompt builders live under `src/milai/llm/prompts/` and are invoked only by their owning state handlers. A single `PersistedState` snapshot (`UserState` + `AppState`) is the canonical persisted source of truth, written atomically to `~/.milai/state.json` after every transition. On launch, the entrypoint loads that snapshot; if one exists, it asks the learner whether to continue it or start a new session that replaces the local snapshot and begins onboarding. A lightweight SRS scheduler reinforces weak skill topics by injecting them into lesson-generation and feedback prompts.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: `textual>=8.2.4` (TUI), `litellm` (provider-agnostic LLM), `pydantic` (data model + structured LLM output), `pyyaml` (config file parsing)
**Storage**: Local JSON file at `~/.milai/state.json` containing `PersistedState`; atomic writes via `tempfile` + `os.replace`
**Testing**: `pytest` (test runner), `ty` (type checker), `ruff` (lint + format), `prek` (pre-commit runner)
**Target Platform**: Linux/macOS terminal (TUI); Docker + FastAPI in v2
**Project Type**: CLI/TUI application
**Performance Goals**: User-facing LLM-backed responses complete within one minute for exercise answers, deviations, and curriculum feedback; local SRS scoring and state transitions should remain simple in-memory operations with no dedicated benchmarking requirement for v1
**Constraints**: Single-user per installation; one active saved learning session; no external service dependencies beyond an LLM provider API; state file must survive crashes (atomic writes); prompt builders must be deterministic functions over explicit state/user inputs
**Scale/Scope**: Single learner; one active target language and curriculum; curriculum of 3-20 modules; skills list grows to approximately 100 topics over time; total state file size under 1 MB; nine workflow states with five LLM-backed prompt families

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Test-First | **Pass with requirement** | Implementation tasks must start with failing tests. Prompt/schema tests must fail before prompt builders are implemented. |
| II. Evidence-Based Validation | **Pass with requirement** | Each state handler must be validated with realistic scripted user input and realistic structured LLM output. End-to-end user-story tests are required before completion. |
| III. DRY | **Pass with watch item** | Prompt-building patterns are expected to repeat. Extract shared prompt utilities only after the pattern appears in three or more prompt modules and the abstraction is stable. |
| IV. YAGNI | **Pass** | No external state-machine library, no SQLite, no sub-agents, and no prompt registry abstraction beyond simple modules/functions for v1. |
| V. Provider Interface | **Pass** | `IOMediator`, `LLMClient`, and `StorageClient` are protocols. State handlers depend on interfaces and prompt builders, never concrete providers. |

No gate violations. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-mvp-tui/
├── plan.md                       # This file
├── research.md                   # Phase 0: model selection, architecture decisions
├── data-model.md                 # Phase 1: UserState document model + state transitions
├── quickstart.md                 # Phase 1: setup, run, test, configuration
├── contracts/
│   ├── io_mediator.md            # IOMediator Protocol + ScriptedMediator test double
│   ├── llm_client.md             # LLMClient Protocol + ScriptedLLMClient test double
│   ├── state_prompts.md          # Handler-owned prompt builder contract
│   └── storage_client.md         # StorageClient Protocol + InMemoryStorage test double
└── tasks.md                      # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
└── milai/
    ├── __init__.py
    ├── main.py                      # entrypoint: loads config/state, offers continue/start-new, wires handlers, runs machine
    ├── config.py                    # Config + LLMConfig + LLMProfilesConfig + StateConfig; loads ~/.milai/config.yaml with defaults
    │
    ├── state/
    │   ├── __init__.py
    │   ├── machine.py               # run() loop: match/case dispatch -> handler.step() -> save PersistedState
    │   ├── variants.py              # AppState discriminated union; all state variant models
    │   └── handlers/
    │       ├── __init__.py
    │       ├── onboarding.py        # OnboardingHandler: user prompts only, no LLM prompt
    │       ├── assessment.py        # owns assessment prompts
    │       ├── assessment_review.py # user confirmation/override only, no LLM prompt
    │       ├── curriculum_gen.py    # owns initial curriculum prompt
    │       ├── curriculum_review.py # owns curriculum adjustment prompt
    │       ├── lesson.py            # owns lesson-generation, dynamic-change, and feedback prompts
    │       ├── deviation.py         # owns free-form conversational prompt
    │       ├── lesson_complete.py   # user progress display only, no LLM prompt
    │       └── curriculum_complete.py # owns extension-module prompt when learner continues
    │
    ├── models/
    │   ├── __init__.py
    │   ├── state.py                 # PersistedState root snapshot
    │   ├── user_state.py            # UserState, UserProfile, Skill
    │   ├── curriculum.py            # Curriculum, Module, Lesson, Exercise
    │   └── assessment.py            # AssessmentQuestion
    │
    ├── io/
    │   ├── __init__.py
    │   ├── mediator.py              # IOMediator Protocol
    │   ├── types.py                 # RichContent, Choice, ContentKind
    │   └── tui/
    │       ├── __init__.py
    │       └── app.py               # TextualMediator: Textual implementation of IOMediator
    │
    ├── llm/
    │   ├── __init__.py
    │   ├── client.py                # LLMClient Protocol
    │   ├── litellm_client.py        # LiteLLMClient: wraps litellm.acompletion
    │   ├── errors.py                # LLMError, LLMParseError
    │   ├── types.py                 # Message, Role
    │   └── prompts/
    │       ├── __init__.py
    │       ├── common.py            # shared prompt fragments after DRY threshold is met
    │       ├── assessment.py        # assessment question + fluency result schemas/prompts
    │       ├── curriculum.py        # initial generation, review adjustment, extension-module schemas/prompts
    │       ├── lesson.py            # lesson content + dynamic-change schemas/prompts
    │       ├── feedback.py          # exercise feedback schema/prompt
    │       └── deviation.py         # bounded conversational prompt
    │
    ├── storage/
    │   ├── __init__.py
    │   ├── client.py                # StorageClient Protocol
    │   ├── local.py                 # LocalStorage (state.json)
    │   └── errors.py                # StorageError
    │
    └── srs/
        ├── __init__.py
        └── scheduler.py             # update_skill(), due_skills(), top_review_skills()

tests/
├── fakes/
│   ├── __init__.py
│   ├── mediator.py                  # ScriptedMediator
│   ├── llm_client.py                # ScriptedLLMClient
│   └── storage_client.py            # InMemoryStorage
├── unit/
│   ├── test_models.py
│   ├── test_srs.py
│   ├── test_state_machine.py
│   ├── test_assessment_prompts.py
│   ├── test_curriculum_prompts.py
│   ├── test_lesson_prompts.py
│   ├── test_feedback_prompts.py
│   └── test_deviation_prompts.py
├── integration/
│   ├── test_storage.py
│   ├── test_llm_client.py
│   ├── test_onboarding_assessment.py
│   ├── test_curriculum_review.py
│   └── test_learning_loop.py
└── contract/
    ├── test_io_mediator.py
    ├── test_llm_contract.py
    ├── test_state_prompts_contract.py
    └── test_storage_contract.py
```

**Structure Decision**: Single-project layout using the `src/` package layout. `src/milai/` is the source package; `tests/` mirrors its structure. The `io/tui/` subdirectory isolates Textual for v1 only. State handlers own workflow behavior and call prompt builders from `llm/prompts/`; prompt builders are deterministic and contain no I/O, storage, provider calls, or config lookup. Three-tier test organisation: unit (fast, no I/O), integration (file system + optional real LLM), contract (Protocol and prompt-shape conformance).

## Complexity Tracking

No violations to justify.

## Design Decisions Summary

Full rationale in [research.md](research.md). Key decisions:

| Decision | Choice | Key reason |
|---|---|---|
| Default LLM profile | `light` profile using `gemini/gemini-2.0-flash` | Good multilingual coverage and cost profile for structured pedagogical content |
| LLM configurability | `~/.milai/config.yaml` with named `llm.profiles`, `llm.default_profile`, and top-level `states.<state>.llm` profile references; env vars for API keys only | Keeps shared model settings DRY and allows open-ended conversation to use a stronger model without making every structured call expensive |
| Workflow architecture | Hand-rolled state machine; `AppState` discriminated union; one constructor-wired handler class per state; `match/case` dispatch; launch-level continue/start-new decision before state-machine entry | Clean domain/workflow separation; resume is simple; per-state dependencies are explicit; no extra workflow state is needed for session selection |
| State prompts | Explicit prompt modules owned by LLM-backed state handlers; deterministic builders; tests before implementation | Keeps prompts reviewable, reusable across TUI/web adapters, and isolated from provider/config concerns |
| Persistence format | JSON at `~/.milai/state.json` | Single-user, tiny dataset; human-readable; no migration complexity; atomic via `os.replace` |
| Spaced repetition | Custom lightweight SM-2-inspired scheduler | Topic-level granularity; feeds LLM prompts rather than driving a separate review session |
| Context management | Stateless per call; deviation capped at 10 exchanges | Predictable token budget; no cross-state context accumulation |
| Sub-agents | None in v1 | All LLM calls are single-turn; curriculum generated in one structured call for coherence |
| Structured LLM output | LiteLLM JSON mode + Pydantic | Provider-agnostic; type-safe; `instructor` available as drop-in if needed |

## Deferred

See [future.md](../future.md) for broader follow-up ideas. Summary:

- `ApiMediator` (FastAPI + WebSocket) and Docker packaging for v2
- LLM telemetry via Langfuse in v2/v3
- Multi-user support with auth and networked persistence
- Durable chronological interaction log if product needs debugging, analytics, or cross-session audit trails
- Shared runtime context object if handler-local retry/control flow becomes duplicated
- Sub-agent parallelism for large curriculum generation if context limits become a real constraint
- `instructor` adoption if LiteLLM JSON mode proves unreliable in practice
