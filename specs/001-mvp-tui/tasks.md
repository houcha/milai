# Tasks: AI-Native Self-Paced Language Learning (milai)

**Input**: Design documents from `/home/bail/Code/milai/specs/001-mvp-tui/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: Required by the specification and constitution. Write each test task first and confirm it fails before the related implementation task.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested as an independent increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and does not depend on incomplete tasks in the same phase
- **[Story]**: User story label for traceability: `[US1]`, `[US2]`, `[US3]`
- Every task includes an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the Python package, dependency, and test layout needed by all feature work.

- [X] T001 Update runtime dependencies and the `milai` console script in `pyproject.toml`
- [X] T002 [P] Create source package directories and package markers under `src/milai/__init__.py`
- [X] T003 [P] Create test package directories and fake package marker under `tests/fakes/__init__.py`
- [X] T004 [P] Add initial usage, configuration, and QA command notes to `README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, protocols, persistence, configuration, fake adapters, and machine loop that all user stories depend on.

**CRITICAL**: No user story work can begin until this phase is complete.

### Foundational Tests

- [X] T005 [P] Add IOMediator protocol conformance tests in `tests/contract/test_io_mediator.py`
- [X] T006 [P] Add LLMClient protocol timeout and error handling contract tests in `tests/contract/test_llm_contract.py`
- [X] T007 [P] Add StorageClient atomic load/save/delete contract tests in `tests/contract/test_storage_contract.py`
- [X] T008 [P] Add state prompt builder contract tests in `tests/contract/test_state_prompts_contract.py`
- [X] T009 [P] Add persisted model invariant and serialization tests in `tests/unit/test_models.py`
- [X] T010 [P] Add SRS scheduler scoring and update tests in `tests/unit/test_srs.py`
- [X] T011 [P] Add state machine persistence/dispatch tests in `tests/unit/test_state_machine.py`
- [X] T012 [P] Add config loading and profile routing tests in `tests/unit/test_config.py`
- [X] T013 [P] Add LiteLLM client parse/error/timeout wrapping tests in `tests/integration/test_llm_client.py`
- [X] T014 [P] Add local storage integration tests using `tmp_path` in `tests/integration/test_storage.py`

### Foundational Implementation

- [X] T015 [P] Implement user-facing content and choice types in `src/milai/io/types.py`
- [X] T016 [P] Implement provider-neutral LLM message types in `src/milai/llm/types.py`
- [X] T017 [P] Implement LLM exception hierarchy in `src/milai/llm/errors.py`
- [X] T018 [P] Implement storage exception hierarchy in `src/milai/storage/errors.py`
- [X] T019 [P] Implement assessment, curriculum, module, lesson, and exercise models in `src/milai/models/curriculum.py`
- [X] T020 [P] Implement assessment question model in `src/milai/models/assessment.py`
- [X] T021 Implement UserState, UserProfile, and Skill models in `src/milai/models/user_state.py`
- [X] T022 Implement PersistedState snapshot model in `src/milai/models/state.py`
- [X] T023 Implement AppState discriminated union variants and transition payload models in `src/milai/state/variants.py`
- [X] T024 [P] Implement IOMediator protocol in `src/milai/io/mediator.py`
- [X] T025 [P] Implement LLMClient protocol in `src/milai/llm/client.py`
- [X] T026 [P] Implement StorageClient protocol in `src/milai/storage/client.py`
- [X] T027 [P] Implement ScriptedMediator test double in `tests/fakes/mediator.py`
- [X] T028 [P] Implement ScriptedLLMClient test double in `tests/fakes/llm_client.py`
- [X] T029 [P] Implement InMemoryStorage test double in `tests/fakes/storage_client.py`
- [X] T030 Implement LocalStorage with atomic JSON writes in `src/milai/storage/local.py`
- [X] T031 Implement SRS update, due, and top-review functions in `src/milai/srs/scheduler.py`
- [X] T032 Implement YAML config defaults and state LLM profile validation in `src/milai/config.py`
- [X] T033 Implement LiteLLMClient structured and chat calls with one-minute user-facing timeout handling in `src/milai/llm/litellm_client.py`
- [X] T034 Implement state machine dispatch, transition persistence, and retry-safe save loop in `src/milai/state/machine.py`
- [X] T035 Implement minimal TuiMediator adapter for mediator methods in `src/milai/io/tui/app.py`
- [X] T036 Implement application entrypoint wiring for config, storage, mediators, clients, and handlers in `src/milai/main.py`

**Checkpoint**: Protocols, models, storage, configuration, fakes, and machine loop are ready for story work.

---

## Phase 3: User Story 1 - Onboarding and Skill Assessment (Priority: P1) MVP

**Goal**: A new or returning learner can provide language preferences, complete or resume an adaptive assessment, and receive a fluency snapshot.

**Independent Test**: Run the onboarding/assessment integration test with scripted mediator and LLM responses; verify a profile, answered assessment questions, skills, and confirmed fluency level are persisted.

### Tests for User Story 1

- [ ] T037 [P] [US1] Add onboarding handler unit tests for required and optional preferences in `tests/unit/test_onboarding_handler.py`
- [ ] T038 [P] [US1] Add assessment prompt unit tests for question and fluency prompts in `tests/unit/test_assessment_prompts.py`
- [ ] T039 [P] [US1] Add assessment handler unit tests for answer capture, resume, fluency calculation, LLM retry, and timeout no-data-loss behavior in `tests/unit/test_assessment_handler.py`
- [ ] T040 [P] [US1] Add assessment review handler unit tests for confirm and override flows in `tests/unit/test_assessment_review_handler.py`
- [ ] T041 [P] [US1] Add end-to-end onboarding-to-assessment integration test in `tests/integration/test_onboarding_assessment.py`
- [ ] T042 [P] [US1] Add saved-session launch choice tests for continue versus start-new in `tests/integration/test_startup_session_choice.py`
- [ ] T043 [P] [US1] Add confirmed replacement tests asserting previous profile, curriculum, and progress are cleared before fresh onboarding in `tests/integration/test_startup_session_choice.py`

### Implementation for User Story 1

- [ ] T044 [US1] Implement OnboardingHandler profile collection and defaults in `src/milai/state/handlers/onboarding.py`
- [ ] T045 [US1] Implement assessment prompt schemas and builders in `src/milai/llm/prompts/assessment.py`
- [ ] T046 [US1] Implement AssessmentHandler question generation, answer persistence, fluency result, retry prompts, and timeout no-data-loss handling in `src/milai/state/handlers/assessment.py`
- [ ] T047 [US1] Implement AssessmentReviewHandler fluency confirmation and override in `src/milai/state/handlers/assessment_review.py`
- [ ] T048 [US1] Implement saved-session continue/start-new launch choice in `src/milai/main.py`
- [ ] T049 [US1] Implement confirmed start-new replacement of profile, curriculum, progress, and app state in `src/milai/main.py`
- [ ] T050 [US1] Wire onboarding, assessment, and assessment review handlers into startup dependencies in `src/milai/main.py`
- [ ] T051 [US1] Wire US1 transitions into the machine dispatch in `src/milai/state/machine.py`
- [ ] T052 [US1] Add TuiMediator rendering for onboarding, assessment choices, and fluency review in `src/milai/io/tui/app.py`

**Checkpoint**: User Story 1 can be completed and tested without curriculum or lesson functionality.

---

## Phase 4: User Story 2 - Curriculum Generation and Review (Priority: P2)

**Goal**: From a confirmed fluency profile, the app generates a structured curriculum and lets the learner reorder, remove, adjust, and confirm modules.

**Independent Test**: Run the curriculum review integration test with a synthetic profile and scripted curriculum responses; verify edited and confirmed curriculum state persists before lessons start.

### Tests for User Story 2

- [ ] T053 [P] [US2] Add curriculum prompt unit tests for generation and adjustment prompts in `tests/unit/test_curriculum_prompts.py`
- [ ] T054 [P] [US2] Add curriculum generation handler unit tests in `tests/unit/test_curriculum_generation_handler.py`
- [ ] T055 [P] [US2] Add curriculum generation LLM failure tests for retry and no-data-loss behavior in `tests/unit/test_curriculum_generation_handler.py`
- [ ] T056 [P] [US2] Add curriculum review handler unit tests for reorder, remove, feedback, confirm, retry, and timeout no-data-loss flows in `tests/unit/test_curriculum_review_handler.py`
- [ ] T057 [P] [US2] Add curriculum review integration test in `tests/integration/test_curriculum_review.py`

### Implementation for User Story 2

- [ ] T058 [US2] Implement curriculum generation and adjustment schemas and builders in `src/milai/llm/prompts/curriculum.py`
- [ ] T059 [US2] Implement CurriculumGenerationHandler structured LLM call and curriculum draft persistence in `src/milai/state/handlers/curriculum_gen.py`
- [ ] T060 [US2] Implement CurriculumReviewHandler confirm, reorder, remove, feedback adjustment, retry, and timeout no-data-loss loop in `src/milai/state/handlers/curriculum_review.py`
- [ ] T061 [US2] Add curriculum review menu rendering and module selection support in `src/milai/io/tui/app.py`
- [ ] T062 [US2] Wire curriculum generation and review handlers into startup dependencies in `src/milai/main.py`
- [ ] T063 [US2] Wire US2 transitions into the machine dispatch in `src/milai/state/machine.py`

**Checkpoint**: User Story 2 can generate, edit, and confirm a curriculum independently from the learning loop.

---

## Phase 5: User Story 3 - Learning Loop (Priority: P3)

**Goal**: The learner can complete lessons with theory, exercises, immediate feedback, SRS reinforcement, free-form deviation, dynamic changes, progress persistence, and curriculum completion extension.

**Independent Test**: Run the learning loop integration test with a confirmed curriculum and scripted LLM responses; verify lesson progress, feedback, deviation return, dynamic change, SRS updates, and curriculum completion state.

### Tests for User Story 3

- [ ] T064 [P] [US3] Add lesson prompt unit tests for lesson content and dynamic change prompts in `tests/unit/test_lesson_prompts.py`
- [ ] T065 [P] [US3] Add feedback prompt unit tests in `tests/unit/test_feedback_prompts.py`
- [ ] T066 [P] [US3] Add deviation prompt unit tests for context window and off-topic boundaries in `tests/unit/test_deviation_prompts.py`
- [ ] T067 [P] [US3] Add lesson handler unit tests for theory, exercises, feedback, feedback timeout no-data-loss behavior, dynamic changes, and SRS updates in `tests/unit/test_lesson_handler.py`
- [ ] T068 [P] [US3] Add deviation handler unit tests for chat, capped context, retry, timeout no-data-loss behavior, and return-to-lesson behavior in `tests/unit/test_deviation_handler.py`
- [ ] T069 [P] [US3] Add lesson and curriculum completion handler unit tests in `tests/unit/test_completion_handlers.py`
- [ ] T070 [P] [US3] Add curriculum completion extension LLM failure tests for retry and no-data-loss behavior in `tests/unit/test_completion_handlers.py`
- [ ] T071 [P] [US3] Add end-to-end learning loop integration test in `tests/integration/test_learning_loop.py`

### Implementation for User Story 3

- [ ] T072 [US3] Implement lesson content and dynamic change schemas and builders in `src/milai/llm/prompts/lesson.py`
- [ ] T073 [US3] Implement exercise feedback schema and builder in `src/milai/llm/prompts/feedback.py`
- [ ] T074 [US3] Implement bounded deviation chat prompt builder in `src/milai/llm/prompts/deviation.py`
- [ ] T075 [US3] Implement LessonHandler theory display, exercise loop, feedback calls, feedback timeout no-data-loss handling, dynamic changes, and retry prompts in `src/milai/state/handlers/lesson.py`
- [ ] T076 [US3] Integrate SRS skill updates and review-skill injection in `src/milai/state/handlers/lesson.py`
- [ ] T077 [US3] Implement DeviationHandler chat loop, timeout no-data-loss handling, capped context window, and return transition in `src/milai/state/handlers/deviation.py`
- [ ] T078 [US3] Implement LessonCompleteHandler cursor advancement and progress summary in `src/milai/state/handlers/lesson_complete.py`
- [ ] T079 [US3] Implement CurriculumCompleteHandler summary, and extension-module generation in `src/milai/state/handlers/curriculum_complete.py`
- [ ] T080 [US3] Add lesson, exercise, deviation, and completion rendering support in `src/milai/io/tui/app.py`
- [ ] T081 [US3] Wire lesson, deviation, and completion handlers into startup dependencies in `src/milai/main.py`
- [ ] T082 [US3] Wire US3 transitions into the machine dispatch in `src/milai/state/machine.py`

**Checkpoint**: All user stories are independently functional and the MVP learning loop is complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, package exports, validation, and final quality checks across all stories.

- [ ] T083 [P] Export public model symbols for tests and handlers in `src/milai/models/__init__.py`
- [ ] T084 [P] Export public state variant symbols in `src/milai/state/__init__.py`
- [ ] T085 [P] Export prompt modules and response models in `src/milai/llm/prompts/__init__.py`
- [ ] T086 [P] Update setup, configuration, reset, and testing documentation in `README.md`
- [ ] T087 [P] Align quickstart commands and configuration details with implementation in `specs/001-mvp-tui/quickstart.md`
- [ ] T088 [P] Add corrupt state recovery and reset confirmation tests in `tests/integration/test_startup_recovery.py`
- [ ] T089 Implement corrupt state recovery and reset confirmation behavior in `src/milai/main.py`
- [ ] T090 Run `uv run pytest tests/unit` and fix failures in `tests/unit/test_state_machine.py`
- [ ] T091 Run `uv run pytest tests/contract` and fix failures in `tests/contract/test_state_prompts_contract.py`
- [ ] T092 Run `uv run pytest tests/integration` and fix failures in `tests/integration/test_learning_loop.py`
- [ ] T093 Run `just type-check-concise` and fix typing issues in `src/milai/state/machine.py`
- [ ] T094 Run `prek run` and fix hook issues in `pyproject.toml`
- [ ] T095 Run `just qa` and fix final QA failures in `pyproject.toml`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup; blocks every user story.
- **User Story 1 (Phase 3)**: Depends on Foundational and is the MVP scope.
- **User Story 2 (Phase 4)**: Depends on Foundational and a synthetic confirmed fluency profile; for product flow, follows US1.
- **User Story 3 (Phase 5)**: Depends on Foundational and a synthetic confirmed curriculum; for product flow, follows US2.
- **Polish (Phase 6)**: Depends on all desired stories for the release.

### User Story Dependencies

- **US1 - Onboarding and Skill Assessment**: No dependency on US2 or US3; can be validated with scripted mediator and LLM responses.
- **US2 - Curriculum Generation and Review**: Can be tested independently using a synthetic `UserState` with confirmed fluency; product flow uses US1 output.
- **US3 - Learning Loop**: Can be tested independently using a synthetic confirmed curriculum; product flow uses US2 output.

### Within Each User Story

- Tests must be written first and fail before implementation.
- Prompt tests precede prompt builders.
- Handler tests precede handler implementation.
- Handlers precede machine and entrypoint wiring.
- TUI rendering tasks happen after mediator-level behavior is clear.

### Parallel Opportunities

- Setup tasks T002-T004 can run in parallel.
- Foundational test tasks T005-T014 can run in parallel.
- Foundational type/protocol/model tasks T015-T029 can run in parallel after tests are in place.
- User story test tasks within each story can run in parallel.
- Prompt implementation tasks can run in parallel with unrelated handler tests after foundational protocols are complete.
- Different user stories can be staffed in parallel after Phase 2 by using synthetic state fixtures, then integrated in priority order.

---

## Parallel Example: User Story 1

```text
Task: "Add onboarding handler unit tests for required and optional preferences in tests/unit/test_onboarding_handler.py"
Task: "Add assessment prompt unit tests for question and fluency prompts in tests/unit/test_assessment_prompts.py"
Task: "Add assessment handler unit tests for answer capture, resume, fluency calculation, LLM retry, and timeout no-data-loss behavior in tests/unit/test_assessment_handler.py"
Task: "Add assessment review handler unit tests for confirm and override flows in tests/unit/test_assessment_review_handler.py"
Task: "Add end-to-end onboarding-to-assessment integration test in tests/integration/test_onboarding_assessment.py"
Task: "Add saved-session launch choice tests for continue versus start-new in tests/integration/test_startup_session_choice.py"
Task: "Add confirmed replacement tests asserting previous profile, curriculum, and progress are cleared before fresh onboarding in tests/integration/test_startup_session_choice.py"
```

## Parallel Example: User Story 2

```text
Task: "Add curriculum prompt unit tests for generation and adjustment prompts in tests/unit/test_curriculum_prompts.py"
Task: "Add curriculum generation handler unit tests in tests/unit/test_curriculum_generation_handler.py"
Task: "Add curriculum generation LLM failure tests for retry and no-data-loss behavior in tests/unit/test_curriculum_generation_handler.py"
Task: "Add curriculum review handler unit tests for reorder, remove, feedback, confirm, retry, and timeout no-data-loss flows in tests/unit/test_curriculum_review_handler.py"
Task: "Add curriculum review integration test in tests/integration/test_curriculum_review.py"
```

## Parallel Example: User Story 3

```text
Task: "Add lesson prompt unit tests for lesson content and dynamic change prompts in tests/unit/test_lesson_prompts.py"
Task: "Add feedback prompt unit tests in tests/unit/test_feedback_prompts.py"
Task: "Add deviation prompt unit tests for context window and off-topic boundaries in tests/unit/test_deviation_prompts.py"
Task: "Add lesson handler unit tests for theory, exercises, feedback, feedback timeout no-data-loss behavior, dynamic changes, and SRS updates in tests/unit/test_lesson_handler.py"
Task: "Add deviation handler unit tests for chat, capped context, retry, timeout no-data-loss behavior, and return-to-lesson behavior in tests/unit/test_deviation_handler.py"
Task: "Add lesson and curriculum completion handler unit tests in tests/unit/test_completion_handlers.py"
Task: "Add curriculum completion extension LLM failure tests for retry and no-data-loss behavior in tests/unit/test_completion_handlers.py"
Task: "Add end-to-end learning loop integration test in tests/integration/test_learning_loop.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundational models, protocols, storage, config, fakes, and machine loop.
3. Complete Phase 3 onboarding and assessment.
4. Stop and validate with `uv run pytest tests/unit/test_onboarding_handler.py tests/unit/test_assessment_handler.py tests/integration/test_onboarding_assessment.py`.

### Incremental Delivery

1. Deliver US1 to validate onboarding, adaptive assessment, resume, and fluency confirmation.
2. Add US2 to validate curriculum generation, human review, and confirmation.
3. Add US3 to validate lesson delivery, feedback, deviation, dynamic changes, SRS reinforcement, and completion extension.
4. Run story-specific tests after each increment, then full `just qa` before release.

### Test-First Execution Rule

Each phase that contains tests must start by adding the relevant failing tests. Implementation begins only after those tests fail for the expected missing behavior, then continues until the tests pass.
