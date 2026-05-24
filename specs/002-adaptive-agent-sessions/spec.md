# Feature Specification: Adaptive Learning Agents

**Feature Branch**: `002-adaptive-agent-sessions`
**Created**: 2026-05-21
**Status**: Draft
**Input**: User description: "currently assessment and curriculum have low adaptiveness; create AssessmentInterviewer and CurriculumDesigner classes that would act like agents that maintain history within assessment and curriculum creation respectively. Refer to specs/agentic.md for details. Also address lesson theory and practice so they become open-ended conversations with questions and changes supported without a separate deviation step."

## Clarifications

### Session 2026-05-21

- Q: Should lesson theory/practice still use the separate deviation flow? → A: Remove deviation flow entirely for lessons.
- Q: What conversation history must persist across assessment, curriculum, and lessons? → A: Store section-scoped LLM messages for assessment, curriculum, and lessons.
- Q: Can curriculum be generated before assessment is complete? → A: Block curriculum until assessment complete.
- Q: What happens after unusable assessment answers? → A: Retry until usable answer.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adaptive Assessment Interview (Priority: P1)

As an onboarding learner, I want assessment to ask one item at a time and adapt from my answers so placement reflects demonstrated ability rather than a fixed prompt batch.

**Why this priority**: Placement drives curriculum quality.

**Independent Test**: Start assessment, answer with varied fluency, and verify each later turn uses prior evidence to ask one next item, retry an unusable answer, or finish with placement.

**Acceptance Scenarios**:

1. **Given** no assessment history, **When** assessment begins, **Then** one initial item is shown and session history starts.
2. **Given** an answered item, **When** assessment continues, **Then** the answer and evidence are recorded before exactly one next outcome is returned: next item, retry, or final placement.
3. **Given** an unusable answer, **When** it is evaluated, **Then** the learner is asked for a usable answer without losing prior context.

---

### User Story 2 - Evidence-Based Curriculum (Priority: P2)

As an assessed learner, I want the curriculum to use my strengths, gaps, goals, and feedback so the path fits my needs and revisions stay coherent.

**Why this priority**: Curriculum is the main learning plan and must not ignore learner evidence.

**Independent Test**: Try curriculum generation before and after completed assessment, then request a targeted revision. Verify incomplete assessment blocks generation, the completed draft reflects learner evidence, and the revision changes the requested area without unrelated churn.

**Acceptance Scenarios**:

1. **Given** completed assessment and learner goals, **When** curriculum is drafted, **Then** focus, order, pacing, or practice emphasis reflects that evidence.
2. **Given** two learners with different histories, **When** curricula are created, **Then** their plans differ in evidence-matched ways.
3. **Given** incomplete assessment, **When** curriculum generation is requested, **Then** generation is blocked until assessment completes.
4. **Given** feedback on a draft section, **When** revision is produced, **Then** the section changes while accepted, unaffected content is preserved.

---

### User Story 3 - Open-Ended Lesson Flow (Priority: P3)

As a learner in a lesson, I want theory and practice to handle questions, clarification, pacing changes, hints, mistakes, and alternate examples inside the lesson flow so lesson interactions never enter a separate deviation flow.

**Why this priority**: Lesson adaptiveness is where personalized curriculum becomes visible.

**Independent Test**: During theory and practice, ask questions, request another explanation, answer incorrectly, and request a different exercise. Verify responses stay contextual and preserve the lesson objective.

**Acceptance Scenarios**:

1. **Given** lesson theory, **When** the learner asks or requests another explanation, **Then** the response uses objective, curriculum context, and lesson history without switching flows.
2. **Given** practice, **When** the learner is wrong, asks why, requests a hint, or asks for another exercise type, **Then** practice gives contextual feedback or adapted practice and records understanding evidence.
3. **Given** a relevant request moves off the planned path, **When** the learner is ready, **Then** the lesson returns to planned progression.

---

### User Story 4 - Resume from Confirmed History (Priority: P4)

As a learner or operator after interruption, I want assessment, curriculum, and lesson sessions to resume from confirmed history so retries do not duplicate prompts or lose context.

**Why this priority**: Adaptive LLM behavior depends on durable section history.

**Independent Test**: Interrupt each workflow after one confirmed turn, retry it, and verify the next result uses confirmed history with no duplicate visible turn, lost input, or conflicting curriculum version.

**Acceptance Scenarios**:

1. **Given** a recorded assessment turn, **When** the next turn is retried, **Then** the prior answer is not duplicated.
2. **Given** a draft and revision feedback, **When** revision is retried, **Then** the same draft and feedback history are used.
3. **Given** a recorded lesson exchange, **When** the next response is retried, **Then** the learner question, answer, or requested change remains available.

### Edge Cases

- Assessment answers are contradictory, repeated, unusable, or insufficient for placement.
- Curriculum is requested before assessment completion.
- Revision feedback references missing or changed draft content.
- Lesson requests are relevant but off sequence, request difficulty or pacing changes, or are unrelated to the current objective.
- Generation fails after learner input but before a confirmed next turn.
- Session resumes after long delay or while other learner histories exist.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide `AssessmentInterviewer`, an adaptive assessment role with ordered history per assessment session.
- **FR-002**: Assessment MUST show at most one unanswered item per active turn.
- **FR-003**: Assessment MUST record each confirmed question and answer in assessment message history before the next adaptive assessment call.
- **FR-004**: Assessment MUST finish with fluency level, rationale, supporting evidence, and existing minimum-evidence and maximum-item policies respected.
- **FR-005**: Assessment MUST retry unusable answers until a usable answer is provided, without discarding history or placing from insufficient evidence.
- **FR-006**: The system MUST provide `CurriculumDesigner`, an adaptive curriculum role with ordered history for drafts, feedback, revisions, and confirmation.
- **FR-007**: Curriculum generation MUST be blocked until assessment completes, then use assessment outcome, learner goals, prior drafts, and feedback to adapt focus, order, pacing, and practice emphasis.
- **FR-008**: Curriculum revisions MUST identify meaningful changes while preserving unaffected accepted content.
- **FR-009**: Lesson theory and practice MUST support open-ended learner questions, clarification, rephrasing, examples, hints, mistake discussion, difficulty changes, and pacing changes inside the current lesson flow.
- **FR-010**: Lesson responses MUST use current curriculum, lesson objective, prior exchanges, and learner performance evidence.
- **FR-011**: Lesson theory and practice MUST NOT enter a separate deviation flow; relevant learner-driven changes are handled inline, and unrelated requests are acknowledged then redirected to the current objective.
- **FR-012**: Assessment, curriculum, and lesson histories MUST store section-scoped LLM messages, remain scoped to the current learner session, and survive retries from the last confirmed state without duplicate prompts, lost input, conflicting versions, or cross-session leakage.

### Key Entities *(include if feature involves data)*

- **Assessment Session**: Learner-specific interview history with assessment messages, questions, answers, and final placement.
- **Curriculum Design Session**: Learner-specific design history with curriculum messages, assessment context, goals, drafts, feedback, revisions, and confirmation status.
- **Curriculum Draft**: Proposed learning plan with units, pacing, focus areas, practice emphasis, and learner-evidence rationale.
- **Lesson Session**: Learner-specific lesson message history tied to a curriculum item, including theory, practice, questions, requested changes, and feedback.
- **Learner-Driven Change**: Request to alter explanation style, pace, examples, practice difficulty, or nearby lesson direction.
- **Section Message History**: Ordered LLM messages scoped to one adaptive section and used for context, traceability, and retry recovery.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Validation covers at least five assessment answer patterns, including strong, weak, mixed, contradictory, and unusable answers; each turn after the first uses prior evidence to choose next item, retry, or final placement.
- **SC-002**: No active assessment validation case shows more than one unanswered item or bypasses existing completion boundaries.
- **SC-003**: Curriculum validation includes pre-assessment generation request, initial draft, and targeted revision; incomplete assessment blocks generation, completed draft reflects learner evidence, and revision preserves unaffected accepted content.
- **SC-004**: Lesson validation includes theory question, rephrasing request, incorrect practice answer, hint request, difficulty change, and unrelated request; none enters a separate deviation flow.
- **SC-005**: Retry validation covers assessment, curriculum revision, and lesson response after confirmed learner input; each resumes without duplicate visible turns, lost input, conflicting versions, or cross-session leakage.
- **SC-006**: Finalized placement, curriculum, and lesson responses are traceable to recorded section histories during review.

## Assumptions

- `AssessmentInterviewer` and `CurriculumDesigner` are workflow role labels; this spec defines observable behavior, not internal structure.
- Existing learner profile, assessment, curriculum review, confirmation, revision, theory, practice, retention, and privacy policies remain in force.
- Lesson theory and practice replace separate deviation handling for all lesson interactions.
