# Implementation Plan: Assessment Framework Logging

**Branch**: `003-assessment-llm-logging` | **Date**: 2026-06-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-assessment-llm-logging/spec.md`

## Summary

Converge on the adaptive framework in assessment before generalizing it to curriculum or lessons. The implementation adds an adaptive assessment interviewer, persists learner data with active workflow state in a shared session wrapper, centralizes LLM completion logging, and adds optional runtime observability for state dispatch and user mediation.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: Pydantic models, LiteLLM-backed provider interface, optional Langfuse tracing
**Storage**: Existing local JSON persistence through the storage client
**Testing**: pytest, ruff, ty, pre-commit via project `just` targets
**Target Platform**: Local TUI application
**Project Type**: Single Python package
**Performance Goals**: No added user-visible latency beyond required LLM calls; tracing must be no-op when disabled
**Constraints**: Use `uv` for Python commands; keep LLM calls behind `LLMClient`; do not require tracing credentials
**Scale/Scope**: One learner session at a time in the current TUI; assessment framework only

## Constitution Check

| Principle | Status |
|---|---|
| Test-First | Pass: assessment, logging, observability, storage, and session changes are covered by focused tests. |
| Evidence-Based Validation | Pass: validation exercises realistic assessment flows and startup/storage recovery. |
| DRY | Pass: LLM completion logging is centralized instead of copied across call sites. |
| YAGNI | Pass: curriculum and lesson agent rewrites are deferred until assessment behavior is evaluated. |
| Provider Interface | Pass: assessment uses `LLMClient`; provider-specific tracing is optional runtime setup. |

## Project Structure

### Documentation (this feature)

```text
specs/003-assessment-llm-logging/
├── plan.md
├── spec.md
├── tasks.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
src/milai/
├── agents/
│   └── assessment.py
├── io/
│   └── tracing.py
├── llm/
│   └── litellm_client.py
├── models/
│   ├── assessment.py
│   └── session.py
├── observability.py
├── state/
│   ├── machine.py
│   └── handlers/
│       └── assessment.py
└── storage/
    ├── client.py
    └── local.py

tests/
├── contract/
├── integration/
└── unit/
```

**Structure Decision**: Keep the existing single-package TUI layout. Add a concrete assessment agent and observability boundaries without introducing a generic agent runtime or new persistence backend.

## Complexity Tracking

No constitution violations.

## Design Decisions

| Area | Decision |
|---|---|
| Scope | Assessment is the only workflow being made adaptive in this feature. Curriculum and lesson rewrites are deferred. |
| Agent shape | Use a concrete `AssessmentInterviewer`; avoid a generic agent abstraction until assessment has produced enough evidence. |
| Session model | Persist `LearningSession` as the recovery boundary containing both learner data and active app state. |
| Assessment policy | Handler enforces one unanswered item, minimum evidence, maximum items, unusable-answer retries, and final placement boundaries. |
| Logging | Centralize completion logging in the LiteLLM client and add assessment diagnostics around outcome decisions. |
| Observability | Configure optional Langfuse tracing when available; otherwise use no-op observability. |
| User mediation tracing | Wrap the mediator to trace prompts, choices, and output boundaries without changing user-facing behavior. |

## Required Validation

Focused commands:

```sh
uv run pytest tests/unit/test_assessment_handler.py tests/unit/test_assessment_prompts.py
uv run pytest tests/integration/test_onboarding_assessment.py
uv run pytest tests/unit/test_observability.py tests/unit/test_tracing_mediator.py tests/unit/test_state_machine.py
uv run pytest tests/integration/test_llm_client.py tests/integration/test_storage.py tests/integration/test_startup_recovery.py
just type-check-concise
prek run
just qa
```
