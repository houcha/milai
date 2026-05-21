# Implementation Plan: Adaptive Learning Agents

**Branch**: `002-adaptive-agent-sessions` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)

## Goal

Make assessment, curriculum design, and lesson interaction adaptive without adding a generic agent framework or new persistence layer.

- Add `AssessmentInterviewer`: one-question assessment turns, answer evidence, retry for unusable answers, final placement with rationale.
- Add `CurriculumDesigner`: draft and revise curricula from completed assessment evidence, learner goals, prior drafts, and feedback.
- Add `LessonTutor`: theory/practice conversation, questions, hints, clarification, difficulty changes, pacing changes, and unrelated redirects happen inline.
- Persist visible messages plus internal observations for assessment, curriculum, and lesson sessions so retries resume from confirmed history.

## Current Architecture Fit

Keep the existing single-package Python 3.12 TUI layout:

```text
src/milai/
├── agents/
│   ├── assessment.py      # new AssessmentInterviewer
│   ├── curriculum.py      # new CurriculumDesigner
│   └── lesson.py          # new LessonTutor for theory and practice
├── llm/
│   └── client.py          # existing provider interface
├── state/
│   ├── variants.py        # persist histories on active workflow states
│   ├── machine.py         # stop routing lesson interactions to deviation
│   └── handlers/
│       ├── assessment.py
│       ├── curriculum_gen.py
│       ├── curriculum_review.py
│       ├── lesson.py
│       └── lesson_practice.py
└── models/
    ├── assessment.py
    ├── curriculum.py
    └── state.py
```

`LessonTutor` should absorb the current `llm/lesson_service.py` responsibilities so there is one place for lesson generation, theory conversation, exercise generation, practice feedback, hints, and adapted practice. Handlers remain thin UI/state coordinators.

No database, event log, generic `Agent` abstraction, duplicate lesson service, or provider-specific imports.

## Design Decisions

| Area | Decision |
|---|---|
| Agent shape | Use concrete `AssessmentInterviewer`, `CurriculumDesigner`, and `LessonTutor`; defer a shared agent abstraction until duplication is proven stable. |
| Lesson agent | Add a concrete `LessonTutor` rather than keeping a parallel `LessonLLM` service. It owns lesson history, lesson content generation, theory conversation, exercise generation, practice feedback, hints, adapted practice, and inline redirect decisions. |
| Persistence | Extend existing persisted app state with ordered history records. Keep `PersistedState` as the only recovery boundary. |
| History contents | Store learner-visible messages separately from internal observations and decisions. |
| Assessment | At most one unanswered item per turn. Handler enforces existing min/max assessment policies. Unusable answers retry until usable. |
| Curriculum | Block generation until assessment is complete. Revisions record feedback and preserve unaffected accepted content. |
| Lessons and practice | Practice is part of `LessonTutor`, not a separate agent. `LessonHandler` and `LessonPracticeHandler` may stay as state handlers, but both delegate lesson intelligence to `LessonTutor`. Inline theory/practice conversation replaces `DeviationState` for lesson interactions. |
| Testing | Use existing scripted mediator/LLM fakes for deterministic realistic flows. |

## Required Validation

Create failing tests before implementation for:

- Assessment answer patterns: strong, weak, mixed, contradictory, unusable.
- Assessment invariant: never more than one unanswered item; no placement before minimum evidence; max item policy respected.
- Curriculum: blocked before completed assessment; draft uses evidence; targeted revision preserves unrelated content.
- Lessons: theory question, rephrase request, incorrect answer, hint request, difficulty change, unrelated request; none enters deviation flow.
- Retry recovery: assessment answer, curriculum feedback, and lesson exchange resume from confirmed history without duplicates or lost input.

Focused commands:

```sh
uv run pytest tests/unit/test_assessment_handler.py
uv run pytest tests/unit/test_curriculum_generation_handler.py tests/unit/test_curriculum_review_handler.py
uv run pytest tests/unit/test_lesson_handler.py tests/unit/test_lesson_practice_handler.py
uv run pytest tests/integration/test_onboarding_assessment.py tests/integration/test_curriculum_review.py tests/integration/test_learning_loop.py
just type-check-concise
prek run
```

## Constitution Check

| Principle | Status |
|---|---|
| Test-First | Pass: implementation must start with failing tests listed above. |
| Evidence-Based Validation | Pass: validate realistic handler flows, not only schemas. |
| DRY | Pass: do not introduce a generic agent runtime yet. |
| YAGNI | Pass: no new storage backend, framework, telemetry, or multi-session service. |
| Provider Interface | Pass: all LLM calls stay behind `LLMClient` and fakes. |

No complexity exceptions.
