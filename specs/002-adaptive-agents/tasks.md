# Tasks: Adaptive Assessment and Curriculum Agents

**Input**: Refactor plan from assessment/curriculum agent design discussion
**Related context**: `specs/001-mvp-tui/issues.md`
**Rule**: One unchecked task equals one commit. Each commit must use Conventional Commits format.

## Format: `[ID] Description`

- Each task includes tests and implementation for one coherent slice.
- Each task must pass its listed verification before commit.
- Do not use `--no-verify`.

---

## Phase 1: Durable Conversation State

- [ ] T001 Add persisted agent message history to workflow states in `src/milai/state/variants.py`, with serialization coverage in `tests/unit/test_models.py`
  - Commit: `refactor(state): persist agent conversation history`
  - Scope: add `agent_messages: list[Message]` to `AssessmentState`, `CurriculumGenerationState`, and `CurriculumReviewState`
  - Verification: `uv run pytest tests/unit/test_models.py`

---

## Phase 2: CurriculumDesigner

- [ ] T002 Add `CurriculumDesigner` generation session in `src/milai/agents/curriculum.py`, and migrate curriculum generation handler/tests to use it
  - Commit: `refactor(curriculum): generate drafts through designer session`
  - Scope: move `CurriculumDraft` to the agent module, add shared curriculum system guidance, persist generated assistant JSON into `CurriculumGenerationState.agent_messages`, update `src/milai/state/handlers/curriculum_gen.py`
  - Verification: `uv run pytest tests/unit/test_curriculum_generation_handler.py tests/unit/test_curriculum_prompts.py`

- [ ] T003 Add `CurriculumDesigner` revision session in `src/milai/agents/curriculum.py`, and migrate curriculum review handler/tests to reuse persisted history
  - Commit: `refactor(curriculum): revise drafts through designer session`
  - Scope: append learner feedback as a user turn, persist revised assistant JSON into `CurriculumReviewState.agent_messages`, keep Confirm/Revise UI behavior unchanged, update `src/milai/state/handlers/curriculum_review.py`
  - Verification: `uv run pytest tests/unit/test_curriculum_review_handler.py tests/integration/test_curriculum_review.py`

- [ ] T004 Route one shared curriculum designer client through startup wiring in `src/milai/main.py`
  - Commit: `refactor(curriculum): share designer client across review flow`
  - Scope: resolve the curriculum designer client from the existing `curriculum_gen` state route and inject it into both generation and review handlers
  - Verification: `uv run pytest tests/integration/test_curriculum_review.py tests/unit/test_config.py`

---

## Phase 3: AssessmentInterviewer

- [ ] T005 Add `AssessmentInterviewer` schemas and conversation methods in `src/milai/agents/assessment.py`
  - Commit: `feat(assessment): add adaptive interviewer session`
  - Scope: add one-question initial turn, answer-evaluation turn, structured fluency result, optional next question, and deterministic assistant JSON history appending
  - Verification: `uv run pytest tests/unit/test_assessment_handler.py`

- [ ] T006 Migrate `AssessmentHandler` to one-question adaptive interviewer turns in `src/milai/state/handlers/assessment.py`
  - Commit: `refactor(assessment): drive placement through interviewer turns`
  - Scope: replace two-question batches with one question at a time, preserve min/max stop policy, keep retry/no-data-loss behavior, persist interviewer history on every successful LLM turn
  - Verification: `uv run pytest tests/unit/test_assessment_handler.py tests/integration/test_onboarding_assessment.py`

---

## Phase 4: Contract Cleanup

- [ ] T007 Replace obsolete assessment/curriculum prompt-builder contracts with agent/session contracts
  - Commit: `test(llm): cover agent sessions instead of prompt builders`
  - Scope: update `tests/contract/test_state_prompts_contract.py`, remove or rewrite obsolete assessment/curriculum prompt unit tests, keep lesson/feedback/deviation prompt contracts unchanged
  - Verification: `uv run pytest tests/contract/test_state_prompts_contract.py tests/unit`

- [ ] T008 Remove unused assessment/curriculum prompt builder code and update references
  - Commit: `refactor(llm): remove migrated prompt builders`
  - Scope: delete unused builder functions from `src/milai/llm/prompts/assessment.py` and `src/milai/llm/prompts/curriculum.py`, update imports to use agent response schemas
  - Verification: `uv run pytest tests/unit tests/integration`

---

## Phase 5: Final QA

- [ ] T009 Run full focused QA and fix any regressions from the agent migration
  - Commit: `chore(qa): stabilize adaptive agent migration`
  - Scope: only commit fixes required by verification; do not add new architecture
  - Verification:
    - `uv run pytest tests/unit/test_assessment_handler.py tests/unit/test_curriculum_generation_handler.py tests/unit/test_curriculum_review_handler.py`
    - `uv run pytest tests/integration/test_onboarding_assessment.py tests/integration/test_curriculum_review.py`
    - `just type-check-concise`
    - `prek run --all-files`

---

## Dependencies

- T001 must land first.
- T002 and T003 must land before T004.
- T005 must land before T006.
- T007 and T008 must wait until both curriculum and assessment handlers no longer depend on the old prompt builders.
- T009 must be last.

## Assumptions

- Use `AssessmentInterviewer` as the corrected class name.
- Persisted LLM message history in local JSON snapshots is acceptable.
- Assessment adaptiveness is more important than preserving the current two-question batching cost profile.
- No generic `Agent` protocol is introduced in this pass.
- Lesson, feedback, and deviation prompt builders remain unchanged.
