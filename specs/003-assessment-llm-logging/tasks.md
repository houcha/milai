---
description: "Tasks for Assessment Framework Logging implementation"
---

# Tasks: Assessment Framework Logging

**Input**: Design documents from `/home/bail/Code/milai/specs/003-assessment-llm-logging/`
**Prerequisites**: `plan.md`, `spec.md`
**Tests**: Required. Assessment behavior, session persistence, completion logging, and observability must be covered before merge.

**Organization**: Tasks are grouped by independently testable user story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches a different file and does not depend on incomplete tasks.
- **[Story]**: Maps task to the user story from `spec.md`.
- Every task includes exact repository paths.

---

## Phase 1: Setup and Session Foundation

**Purpose**: Establish the assessment package and shared session recovery boundary.

- [X] T001 Create concrete agent package exports in `src/milai/agents/__init__.py`
- [X] T002 [P] Add scripted adaptive assessment fakes in `tests/fakes/adaptive_agents.py`
- [X] T003 [P] Add adaptive assessment fixtures in `tests/fakes/adaptive_scenarios.py`
- [X] T004 Add `LearningSession` as the persisted learner plus active-state wrapper in `src/milai/models/session.py`
- [X] T005 Update storage contracts and fakes to save/load `LearningSession` in `src/milai/storage/client.py`, `src/milai/storage/local.py`, `tests/fakes/storage_client.py`, and `tests/contract/test_storage_contract.py`
- [X] T006 Update startup and state-machine dispatch to operate on `LearningSession` in `src/milai/main.py` and `src/milai/state/machine.py`
- [X] T007 Add model, storage, startup, and session-choice coverage in `tests/unit/test_models.py`, `tests/integration/test_storage.py`, `tests/integration/test_startup_recovery.py`, and `tests/integration/test_startup_session_choice.py`

**Checkpoint**: Existing workflows can persist and resume through the shared session boundary.

---

## Phase 2: User Story 1 - Adaptive Assessment Interview (Priority: P1) MVP

**Goal**: Assessment asks one item at a time, records evidence, retries unusable answers, and produces placement only after policy-compliant evidence.

**Independent Test**: Start assessment, answer with varied fluency, and verify each later turn uses prior evidence to ask one next item, retry an unusable answer, or finish with placement.

### Tests for User Story 1

- [X] T008 [P] [US1] Add assessment interviewer prompt/schema tests in `tests/unit/test_assessment_prompts.py`
- [X] T009 [P] [US1] Add adaptive assessment handler tests for strong, weak, mixed, contradictory, unusable, min-item, max-item, and one-unanswered-item cases in `tests/unit/test_assessment_handler.py`
- [X] T010 [P] [US1] Add onboarding adaptive assessment integration coverage in `tests/integration/test_onboarding_assessment.py`

### Implementation for User Story 1

- [X] T011 [P] [US1] Add assessment evidence, answer evaluation, retry, next-item, and placement result models in `src/milai/models/assessment.py`
- [X] T012 [US1] Implement `AssessmentInterviewer` with assessment history input, answer evaluation, next-item selection, unusable-answer retry, and placement output in `src/milai/agents/assessment.py`
- [X] T013 [US1] Refactor `AssessmentHandler` to delegate adaptive assessment turns, keep at most one unanswered item, record confirmed question/answer messages, and enforce existing min/max assessment policies in `src/milai/state/handlers/assessment.py`
- [X] T014 [US1] Update assessment review handoff and related state variants in `src/milai/state/handlers/assessment_review.py` and `src/milai/state/variants.py`

**Checkpoint**: Adaptive assessment works independently and can ship as the MVP slice.

---

## Phase 3: User Story 2 - Inspect Assessment Decisions (Priority: P2)

**Goal**: Assessment decisions, model calls, state dispatches, and user mediation are reviewable through logs or optional traces.

**Independent Test**: Run assessment with logging enabled and verify assessment diagnostics, LLM completion metadata, state dispatch spans, and user mediation spans are available for review without exposing secrets.

### Tests for User Story 2

- [X] T015 [P] [US2] Add LLM completion logging coverage in `tests/integration/test_llm_client.py`
- [X] T016 [P] [US2] Add runtime observability configuration tests in `tests/unit/test_observability.py`
- [X] T017 [P] [US2] Add user mediation tracing tests in `tests/unit/test_tracing_mediator.py`
- [X] T018 [P] [US2] Add state dispatch observability tests in `tests/unit/test_state_machine.py`

### Implementation for User Story 2

- [X] T019 [US2] Centralize completion logging and provider error logging in `src/milai/llm/litellm_client.py`
- [X] T020 [US2] Add assessment diagnostics for answer evaluation, next question, retry, final placement, and provider errors in `src/milai/state/handlers/assessment.py`
- [X] T021 [US2] Add optional runtime observability setup in `src/milai/observability.py`
- [X] T022 [US2] Add tracing wrapper for user-facing mediator interactions in `src/milai/io/tracing.py`
- [X] T023 [US2] Wire observability and tracing into startup in `src/milai/main.py`
- [X] T024 [US2] Document logging and tracing configuration in `README.md`, `AGENTS.md`, `.gitignore`, and `pyproject.toml`

**Checkpoint**: Assessment behavior can be inspected locally and through optional tracing.

---

## Phase 4: User Story 3 - Preserve Session Boundaries (Priority: P3)

**Goal**: Saved sessions resume from confirmed state without duplicate prompts, lost active workflow state, or cross-session leakage.

**Independent Test**: Persist and reload active sessions across onboarding, assessment, curriculum, lesson, and completion states, then verify the restored session contains the expected user data and active state.

### Tests for User Story 3

- [X] T025 [P] [US3] Add storage round-trip coverage for `LearningSession` in `tests/contract/test_storage_contract.py` and `tests/integration/test_storage.py`
- [X] T026 [P] [US3] Add startup recovery coverage for saved sessions in `tests/integration/test_startup_recovery.py`
- [X] T027 [P] [US3] Add startup session choice coverage in `tests/integration/test_startup_session_choice.py`
- [X] T028 [P] [US3] Update handler tests to pass `LearningSession` through active state transitions in `tests/unit/`

### Implementation for User Story 3

- [X] T029 [US3] Update all state handlers to accept and return `LearningSession` boundaries in `src/milai/state/handlers/`
- [X] T030 [US3] Update state machine save/dispatch behavior to persist `LearningSession` in `src/milai/state/machine.py`
- [X] T031 [US3] Update main startup recovery to create or resume `LearningSession` in `src/milai/main.py`
- [X] T032 [US3] Keep current curriculum and lesson behavior compatible with the new session boundary without broad adaptive rewrites in `src/milai/state/handlers/curriculum_gen.py`, `src/milai/state/handlers/curriculum_review.py`, `src/milai/state/handlers/lesson.py`, and `src/milai/state/handlers/lesson_practice.py`

**Checkpoint**: Assessment-first framework changes do not break existing workflows.

---

## Phase 5: Polish and Validation

**Purpose**: Final validation, cleanup, and documentation for merge readiness.

- [X] T033 [P] Add Langfuse project guidance in `.agents/skills/langfuse/`
- [X] T034 [P] Add Codex project guidance in `.codex/config.toml`
- [X] T035 Run focused assessment validation with `uv run pytest tests/unit/test_assessment_handler.py tests/unit/test_assessment_prompts.py tests/integration/test_onboarding_assessment.py`
- [X] T036 Run observability validation with `uv run pytest tests/unit/test_observability.py tests/unit/test_tracing_mediator.py tests/unit/test_state_machine.py`
- [X] T037 Run storage and startup validation with `uv run pytest tests/contract/test_storage_contract.py tests/integration/test_storage.py tests/integration/test_startup_recovery.py tests/integration/test_startup_session_choice.py`
- [X] T038 Run type checking with `just type-check-concise`
- [X] T039 Run pre-commit hooks with `prek run`
- [X] T040 Run full QA with `just qa`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup and Session Foundation (Phase 1)**: No dependencies.
- **US1 Adaptive Assessment (Phase 2)**: Depends on session foundation.
- **US2 Inspect Assessment Decisions (Phase 3)**: Can start after session foundation, but assessment diagnostics depend on US1 handler behavior.
- **US3 Preserve Session Boundaries (Phase 4)**: Depends on session foundation and validates compatibility across existing workflows.
- **Polish (Phase 5)**: Depends on desired user stories being implemented.

### User Story Dependencies

- **US1 (P1)**: Required MVP for this branch.
- **US2 (P2)**: Builds on US1 to make assessment decisions reviewable.
- **US3 (P3)**: Supports US1 and protects existing workflows.

### Parallel Opportunities

- T002 and T003 can run in parallel after T001.
- T015, T016, T017, and T018 can run in parallel because they cover separate observability surfaces.
- T025, T026, and T027 can run in parallel after `LearningSession` exists.
- Focused validations in Phase 5 can run independently before `just qa`.

## Implementation Strategy

1. Establish `LearningSession` so assessment and existing workflows share one persistence boundary.
2. Deliver adaptive assessment as the only behavior-changing agent slice.
3. Add diagnostics, completion logging, and optional tracing to evaluate assessment behavior.
4. Keep curriculum and lesson behavior compatible, but defer their adaptive redesign to later specifications.
5. Validate with focused tests and full QA before merging.

## Notes

- Use `uv` for Python commands. Do not invoke `python`, `pip`, or `pip install`.
- Do not add a generic agent framework, new persistence backend, or required tracing service.
- Keep all LLM calls behind `LLMClient`.
- Treat assessment diagnostics as the evidence source for deciding whether to generalize the framework.
