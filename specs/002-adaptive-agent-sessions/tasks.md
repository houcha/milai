---
description: "Tasks for Adaptive Learning Agents implementation"
---

# Tasks: Adaptive Learning Agents

**Input**: Design documents from `/home/bail/Code/milai/specs/002-adaptive-agent-sessions/`
**Prerequisites**: `plan.md`, `spec.md`
**Optional Docs Present**: none from `research.md`, `data-model.md`, `contracts/`, or `quickstart.md`
**Tests**: Required. The implementation plan explicitly requires failing tests before implementation.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested as an independent increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches a different file and does not depend on incomplete tasks.
- **[Story]**: Maps task to the user story from `spec.md`.
- Every task includes exact repository paths.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare concrete agent package and test support locations.

- [X] T001 Create concrete agent package exports in `src/milai/agents/__init__.py`
- [X] T002 [P] Add reusable scripted adaptive-agent fakes in `tests/fakes/adaptive_agents.py`
- [X] T003 [P] Add shared adaptive-flow fixtures for assessment, curriculum, and lessons in `tests/fakes/adaptive_scenarios.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared durable history and state shape required by assessment, curriculum, and lessons.

**CRITICAL**: No user story implementation should start until this phase is complete.

- [ ] T004 [P] Add shared `VisibleMessage`, `InternalObservation`, `AgentDecision`, and `AgentHistoryRecord` Pydantic models in `src/milai/models/agent_history.py`
- [ ] T005 [P] Add serialization and validation coverage for shared agent history records in `tests/unit/test_models.py`
- [ ] T006 Extend adaptive workflow states with ordered history fields in `src/milai/state/variants.py`
- [ ] T007 Add persisted `AppState` round-trip coverage for assessment, curriculum, and lesson histories in `tests/unit/test_models.py`

**Checkpoint**: Foundation ready. User story implementation can begin.

---

## Phase 3: User Story 1 - Adaptive Assessment Interview (Priority: P1) MVP

**Goal**: Assessment asks one item at a time, records evidence, retries unusable answers, and produces placement only after policy-compliant evidence.

**Independent Test**: Start assessment, answer with varied fluency, and verify each later turn uses prior evidence to ask one next item, retry an unusable answer, or finish with placement.

### Tests for User Story 1

- [ ] T008 [P] [US1] Add `AssessmentInterviewer` prompt/schema tests for single-turn outcomes in `tests/unit/test_assessment_prompts.py`
- [ ] T009 [P] [US1] Add adaptive assessment handler tests for strong, weak, mixed, contradictory, unusable, min-item, max-item, and one-unanswered-item cases in `tests/unit/test_assessment_handler.py`
- [ ] T010 [P] [US1] Add onboarding adaptive assessment integration coverage for one-question turns and final placement rationale in `tests/integration/test_onboarding_assessment.py`

### Implementation for User Story 1

- [ ] T011 [P] [US1] Add assessment evidence, answer evaluation, retry, next-item, and placement result models in `src/milai/models/assessment.py`
- [ ] T012 [US1] Implement `AssessmentInterviewer` with `LLMClient` calls, assessment history input, answer evaluation, next-item selection, unusable-answer retry, and placement output in `src/milai/agents/assessment.py`
- [ ] T013 [US1] Update assessment prompt builders and structured response schemas to request exactly one outcome per turn in `src/milai/llm/prompts/assessment.py`
- [ ] T014 [US1] Refactor `AssessmentHandler` to delegate adaptive decisions to `AssessmentInterviewer`, keep at most one unanswered item, record evidence and decisions, and enforce existing min/max assessment policies in `src/milai/state/handlers/assessment.py`

**Checkpoint**: User Story 1 works independently and can ship as MVP.

---

## Phase 4: User Story 2 - Evidence-Based Curriculum (Priority: P2)

**Goal**: Curriculum generation is blocked before completed assessment, then drafts and revisions use evidence, goals, prior drafts, and feedback while preserving unrelated accepted content.

**Independent Test**: Try curriculum generation before and after completed assessment, then request targeted revision. Verify incomplete assessment blocks generation, completed draft reflects learner evidence, and revision changes only requested areas.

### Tests for User Story 2

- [ ] T015 [P] [US2] Add curriculum generation tests for incomplete-assessment blocking and evidence-matched drafts in `tests/unit/test_curriculum_generation_handler.py`
- [ ] T016 [P] [US2] Add targeted revision tests for feedback history and unrelated-content preservation in `tests/unit/test_curriculum_review_handler.py`
- [ ] T017 [P] [US2] Add curriculum generation and revision integration coverage with distinct learner histories in `tests/integration/test_curriculum_review.py`

### Implementation for User Story 2

- [ ] T018 [P] [US2] Add curriculum draft rationale, revision summary, feedback record, and design history models in `src/milai/models/curriculum.py`
- [ ] T019 [US2] Implement `CurriculumDesigner` with draft, revision, evidence-use, and preservation behavior in `src/milai/agents/curriculum.py`
- [ ] T020 [US2] Update curriculum prompt builders and schemas to include assessment evidence, learner goals, prior drafts, feedback history, and preservation instructions in `src/milai/llm/prompts/curriculum.py`
- [ ] T021 [US2] Refactor `CurriculumGenerationHandler` to block incomplete assessment, delegate draft generation to `CurriculumDesigner`, and append draft history in `src/milai/state/handlers/curriculum_gen.py`
- [ ] T022 [US2] Refactor `CurriculumReviewHandler` to record feedback, delegate targeted revision to `CurriculumDesigner`, and preserve accepted content in `src/milai/state/handlers/curriculum_review.py`
- [ ] T023 [US2] Carry completed assessment evidence and assessment history into curriculum generation state in `src/milai/state/handlers/assessment_review.py`

**Checkpoint**: User Story 2 works independently with a completed-assessment fixture and integrates after US1.

---

## Phase 5: User Story 3 - Open-Ended Lesson Flow (Priority: P3)

**Goal**: Theory and practice handle questions, clarification, rephrasing, hints, mistakes, difficulty changes, pacing changes, alternate examples, and unrelated redirects inline without `DeviationState`.

**Independent Test**: During theory and practice, ask questions, request another explanation, answer incorrectly, request a hint, request difficulty change, and make an unrelated request. Verify all responses stay in lesson flow and preserve the lesson objective.

### Tests for User Story 3

- [ ] T024 [P] [US3] Add `LessonTutor` tests for theory question, rephrase request, alternate example, difficulty change, pacing change, and unrelated redirect in `tests/unit/test_lesson_tutor.py`
- [ ] T025 [P] [US3] Update lesson handler tests so Ask and Change choices never return `DeviationState` and theory conversation stays contextual in `tests/unit/test_lesson_handler.py`
- [ ] T026 [P] [US3] Update practice handler tests for incorrect answer, why question, hint request, another exercise type, adapted practice, and evidence recording in `tests/unit/test_lesson_practice_handler.py`
- [ ] T027 [P] [US3] Update learning loop integration to remove `DeviationHandler` from lesson interactions and keep all lesson requests inline in `tests/integration/test_learning_loop.py`

### Implementation for User Story 3

- [ ] T028 [P] [US3] Add lesson interaction request, tutor reply, practice action, and learning observation models in `src/milai/models/curriculum.py`
- [ ] T029 [US3] Implement `LessonTutor` for lesson generation, theory conversation, exercise generation, practice feedback, hints, adapted practice, and inline redirects in `src/milai/agents/lesson.py`
- [ ] T030 [US3] Refactor `LessonHandler` to delegate learner questions, rephrases, examples, pacing changes, difficulty changes, and unrelated requests to `LessonTutor` without returning `DeviationState` in `src/milai/state/handlers/lesson.py`
- [ ] T031 [US3] Refactor `LessonPracticeHandler` to delegate answers, hint requests, why questions, and exercise changes to `LessonTutor` while recording learning observations in `src/milai/state/handlers/lesson_practice.py`
- [ ] T032 [US3] Replace lesson service wiring with `LessonTutor` construction in `src/milai/main.py`
- [ ] T033 [US3] Remove direct lesson flow dependency on `LessonLLM` by deleting or reducing `src/milai/llm/lesson_service.py` to a compatibility import after handlers and tests use `src/milai/agents/lesson.py`

**Checkpoint**: User Story 3 works independently with a confirmed curriculum fixture and no lesson interaction enters deviation flow.

---

## Phase 6: User Story 4 - Resume from Confirmed History (Priority: P4)

**Goal**: Assessment, curriculum, and lesson sessions resume from confirmed history without duplicate prompts, lost input, conflicting curriculum versions, or cross-session leakage.

**Independent Test**: Interrupt each workflow after one confirmed turn, retry it, and verify next result uses confirmed history exactly once.

### Tests for User Story 4

- [ ] T034 [P] [US4] Add assessment retry recovery tests for confirmed answer history without duplicate visible prompts in `tests/unit/test_assessment_handler.py`
- [ ] T035 [P] [US4] Add curriculum revision retry recovery tests for stable draft and feedback history in `tests/unit/test_curriculum_review_handler.py`
- [ ] T036 [P] [US4] Add lesson exchange retry recovery tests for confirmed learner question, answer, and requested change history in `tests/unit/test_lesson_practice_handler.py`
- [ ] T037 [P] [US4] Add persisted resume regression coverage for assessment, curriculum, and lesson histories in `tests/integration/test_startup_recovery.py`

### Implementation for User Story 4

- [ ] T038 [US4] Update assessment retry persistence so `AssessmentHandler` stores confirmed visible answer and internal observation before the next adaptive decision without duplicate prompts in `src/milai/state/handlers/assessment.py`
- [ ] T039 [US4] Update curriculum draft retry persistence so `CurriculumGenerationHandler` reuses confirmed assessment and draft history without conflicting versions in `src/milai/state/handlers/curriculum_gen.py`
- [ ] T040 [US4] Update curriculum feedback retry persistence so `CurriculumReviewHandler` reuses confirmed feedback and prior draft history without losing accepted content in `src/milai/state/handlers/curriculum_review.py`
- [ ] T041 [US4] Update lesson theory retry persistence so `LessonHandler` reuses confirmed learner requests, tutor replies, and internal observations without duplicate visible turns in `src/milai/state/handlers/lesson.py`
- [ ] T042 [US4] Update lesson practice retry persistence so `LessonPracticeHandler` reuses confirmed answers, hints, feedback, and learning observations without lost input in `src/milai/state/handlers/lesson_practice.py`

**Checkpoint**: All adaptive histories survive retry and resume through persisted app state.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, cleanup, and documentation after desired user stories are complete.

- [ ] T043 [P] Update any adaptive-agent developer notes for the feature in `specs/002-adaptive-agent-sessions/plan.md`
- [ ] T044 Run assessment validation with `uv run pytest tests/unit/test_assessment_handler.py tests/integration/test_onboarding_assessment.py` from `/home/bail/Code/milai`
- [ ] T045 Run curriculum validation with `uv run pytest tests/unit/test_curriculum_generation_handler.py tests/unit/test_curriculum_review_handler.py tests/integration/test_curriculum_review.py` from `/home/bail/Code/milai`
- [ ] T046 Run lesson validation with `uv run pytest tests/unit/test_lesson_tutor.py tests/unit/test_lesson_handler.py tests/unit/test_lesson_practice_handler.py tests/integration/test_learning_loop.py` from `/home/bail/Code/milai`
- [ ] T047 Run retry recovery validation with `uv run pytest tests/integration/test_startup_recovery.py` from `/home/bail/Code/milai`
- [ ] T048 Run type checking with `just type-check-concise` from `/home/bail/Code/milai`
- [ ] T049 Run pre-commit hooks with `prek run` from `/home/bail/Code/milai`
- [ ] T050 Run full QA with `just qa` from `/home/bail/Code/milai`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. Blocks all user stories.
- **US1 Adaptive Assessment (Phase 3)**: Depends on Foundational. Recommended MVP.
- **US2 Evidence-Based Curriculum (Phase 4)**: Depends on Foundational and can use completed-assessment fixtures, but production integration depends on US1 handoff.
- **US3 Open-Ended Lesson Flow (Phase 5)**: Depends on Foundational and can use confirmed-curriculum fixtures.
- **US4 Resume from Confirmed History (Phase 6)**: Depends on US1, US2, and US3 because it validates all adaptive histories.
- **Polish (Phase 7)**: Depends on all desired user stories.

### User Story Dependencies

- **US1 (P1)**: No story dependencies after Foundational.
- **US2 (P2)**: Independently testable with completed-assessment fixtures; production flow builds on US1.
- **US3 (P3)**: Independently testable with confirmed-curriculum fixtures.
- **US4 (P4)**: Cross-story reliability story; complete after US1-US3.

### Within Each User Story

- Write tests first and verify they fail.
- Add or extend models before agent classes.
- Implement agent classes before handler delegation.
- Update integration handoff after unit behavior is complete.
- Validate story independently before moving to lower-priority stories.

---

## Parallel Opportunities

- T002 and T003 can run in parallel after T001 because they touch different test-support files.
- T004 and T005 can run in parallel, then T006 and T007 complete the shared state foundation.
- US1 test tasks T008, T009, and T010 can run in parallel before implementation.
- US2 test tasks T015, T016, and T017 can run in parallel before implementation.
- US3 test tasks T024, T025, T026, and T027 can run in parallel before implementation.
- US4 test tasks T034, T035, T036, and T037 can run in parallel after US1-US3 behavior exists.
- After Foundational, US1 and US3 can be staffed in parallel; US2 can start with fixtures while waiting for US1 handoff.

---

## Parallel Example: User Story 1

```bash
Task: "Add `AssessmentInterviewer` prompt/schema tests for single-turn outcomes in tests/unit/test_assessment_prompts.py"
Task: "Add adaptive assessment handler tests for strong, weak, mixed, contradictory, unusable, min-item, max-item, and one-unanswered-item cases in tests/unit/test_assessment_handler.py"
Task: "Add onboarding adaptive assessment integration coverage for one-question turns and final placement rationale in tests/integration/test_onboarding_assessment.py"
```

## Parallel Example: User Story 2

```bash
Task: "Add curriculum generation tests for incomplete-assessment blocking and evidence-matched drafts in tests/unit/test_curriculum_generation_handler.py"
Task: "Add targeted revision tests for feedback history and unrelated-content preservation in tests/unit/test_curriculum_review_handler.py"
Task: "Add curriculum generation and revision integration coverage with distinct learner histories in tests/integration/test_curriculum_review.py"
```

## Parallel Example: User Story 3

```bash
Task: "Add `LessonTutor` tests for theory question, rephrase request, alternate example, difficulty change, pacing change, and unrelated redirect in tests/unit/test_lesson_tutor.py"
Task: "Update lesson handler tests so Ask and Change choices never return `DeviationState` and theory conversation stays contextual in tests/unit/test_lesson_handler.py"
Task: "Update practice handler tests for incorrect answer, why question, hint request, another exercise type, adapted practice, and evidence recording in tests/unit/test_lesson_practice_handler.py"
Task: "Update learning loop integration to remove `DeviationHandler` from lesson interactions and keep all lesson requests inline in tests/integration/test_learning_loop.py"
```

## Parallel Example: User Story 4

```bash
Task: "Add assessment retry recovery tests for confirmed answer history without duplicate visible prompts in tests/unit/test_assessment_handler.py"
Task: "Add curriculum revision retry recovery tests for stable draft and feedback history in tests/unit/test_curriculum_review_handler.py"
Task: "Add lesson exchange retry recovery tests for confirmed learner question, answer, and requested change history in tests/unit/test_lesson_practice_handler.py"
Task: "Add persisted resume regression coverage for assessment, curriculum, and lesson histories in tests/integration/test_startup_recovery.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 tests and verify they fail.
3. Implement Phase 3 assessment models, `AssessmentInterviewer`, prompts, and handler delegation.
4. Run `uv run pytest tests/unit/test_assessment_handler.py tests/integration/test_onboarding_assessment.py`.
5. Stop and validate assessment behavior before curriculum and lesson work.

### Incremental Delivery

1. Deliver US1 adaptive assessment and validate placement rationale.
2. Deliver US2 curriculum generation and targeted revisions using completed assessment evidence.
3. Deliver US3 lesson conversations and remove lesson deviation routing.
4. Deliver US4 retry/resume reliability across all adaptive histories.
5. Run focused validations, then `just type-check-concise`, `prek run`, and `just qa`.

### Parallel Team Strategy

1. One developer completes shared history models and state variants.
2. Separate developers write failing tests for US1, US2, and US3 in parallel.
3. Implementation proceeds by story with ownership over distinct files.
4. US4 begins after story handlers expose confirmed history behavior.

---

## Notes

- Use `uv` for Python commands. Do not invoke `python`, `pip`, or `pip install`.
- Do not add a generic agent framework, new persistence layer, database, provider-specific imports, or duplicate lesson service.
- Keep all LLM calls behind `LLMClient`.
- Keep handlers thin; concrete agents own adaptive LLM prompts and decisions.
- Visible learner messages and internal observations must be stored separately and scoped to the current persisted app state.
- Commit after each completed task or logical group with Conventional Commits format.
