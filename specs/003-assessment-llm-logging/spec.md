# Feature Specification: Assessment Framework Logging

**Feature Branch**: `003-assessment-llm-logging`
**Created**: 2026-06-05
**Status**: Draft
**Input**: User description: "Drift from the broad adaptive-agent spec and converge first on the best framework for one part of the app: assessment. Add logging/observability so assessment behavior can be inspected before re-implementing all states."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adaptive Assessment Interview (Priority: P1)

As an onboarding learner, I want assessment to ask one item at a time and adapt from my answers so placement reflects demonstrated ability rather than a fixed prompt batch.

**Why this priority**: Assessment quality drives every later curriculum decision, and it is the smallest workflow where the adaptive framework can be validated end to end.

**Independent Test**: Start onboarding assessment, answer with varied fluency, and verify each later turn uses prior evidence to ask one next item, retry an unusable answer, or finish with placement.

**Acceptance Scenarios**:

1. **Given** no assessment history, **When** assessment begins, **Then** one initial item is shown and assessment history starts.
2. **Given** an answered item, **When** assessment continues, **Then** the answer and evidence are recorded before exactly one next outcome is returned: next item, retry, or final placement.
3. **Given** an unusable answer, **When** it is evaluated, **Then** the learner is asked for a usable answer without losing prior context.
4. **Given** sufficient evidence for placement, **When** assessment completes, **Then** the learner receives a fluency level with rationale and supporting evidence.

---

### User Story 2 - Inspect Assessment Decisions (Priority: P2)

As an operator improving assessment prompts, I want assessment decisions, LLM calls, and user-visible turns to be logged so I can evaluate whether the framework is producing useful behavior before applying it to curriculum or lessons.

**Why this priority**: The branch intentionally evaluates one workflow first. Without diagnostics and tracing, the team cannot tell whether assessment adaptiveness is worth generalizing.

**Independent Test**: Run assessment with logging enabled and verify assessment diagnostics, LLM completion metadata, state dispatch spans, and user mediation spans are available for review without exposing secrets.

**Acceptance Scenarios**:

1. **Given** assessment starts, **When** a first question is generated, **Then** diagnostics record that an assessment turn began and what outcome type was produced.
2. **Given** a learner answer is submitted, **When** the assessment call completes, **Then** logs include enough metadata to connect the prior prompt, model call, and resulting assessment outcome.
3. **Given** observability credentials are configured, **When** the app runs, **Then** state dispatches and user-facing mediator interactions are traced.
4. **Given** observability credentials are absent or disabled, **When** the app runs, **Then** tracing is skipped without breaking assessment.

---

### User Story 3 - Preserve Session Boundaries (Priority: P3)

As a learner returning after interruption, I want the app to resume from the last confirmed session state so assessment does not duplicate prompts, lose answers, or mix unrelated workflow state.

**Why this priority**: Assessment adaptiveness depends on ordered history and reliable recovery. This session boundary is the candidate framework for later workflows.

**Independent Test**: Persist and reload active sessions across onboarding, assessment, curriculum, lesson, and completion states, then verify the restored session contains the expected user data and active state.

**Acceptance Scenarios**:

1. **Given** an assessment turn has been confirmed, **When** the session is saved and loaded, **Then** the assessment question, answer, and message history remain available.
2. **Given** a non-assessment workflow is active, **When** the session is saved and loaded, **Then** the active workflow resumes through the shared session wrapper.
3. **Given** a saved session is missing or invalid, **When** the app starts, **Then** it can fall back to a fresh onboarding session.

### Edge Cases

- Assessment answers are contradictory, repeated, unusable, or insufficient for placement.
- The model suggests placement before minimum evidence is available.
- The model suggests another question after the maximum item policy has been reached.
- Logging or tracing is disabled, partially configured, or unavailable at runtime.
- LLM calls fail after learner input but before a confirmed next turn.
- A saved session is absent, stale, or uses a different active workflow state.
- Diagnostic data must be useful for review without leaking credentials or provider secrets.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an adaptive assessment interview that keeps ordered assessment history per learner session.
- **FR-002**: Assessment MUST show at most one unanswered item per active turn.
- **FR-003**: Assessment MUST record each confirmed question and answer before requesting the next adaptive assessment outcome.
- **FR-004**: Assessment MUST finish with fluency level, rationale, supporting evidence, and existing minimum-evidence and maximum-item policies respected.
- **FR-005**: Assessment MUST retry unusable answers until a usable answer is provided, without discarding history or placing from insufficient evidence.
- **FR-006**: Assessment diagnostics MUST record assessment turn starts, answer evaluations, next-question outcomes, retry outcomes, final-placement outcomes, and provider errors in reviewable logs.
- **FR-007**: LLM completion logging MUST centralize model-call metadata so assessment behavior can be evaluated consistently across providers.
- **FR-008**: Runtime observability MUST be optional and MUST degrade to no-op behavior when tracing credentials or tracing support are unavailable.
- **FR-009**: When runtime observability is enabled, the system MUST trace state dispatches and user-facing input/output mediation with enough context to connect them to a learner session and active workflow.
- **FR-010**: The persisted session model MUST keep learner data and active workflow state together so saved sessions can resume from one recovery boundary.
- **FR-011**: Storage MUST save and load the persisted session model without cross-session leakage or loss of active workflow state.
- **FR-012**: Curriculum and lesson adaptiveness beyond session compatibility and existing behavior are explicitly out of scope for this feature.

### Key Entities *(include if feature involves data)*

- **Learning Session**: Persisted learner data plus one active workflow state used as the recovery boundary for startup and dispatch.
- **Assessment Session State**: Assessment workflow state containing current question, prior answers, assessment messages, and final placement data when complete.
- **Assessment Outcome**: One model-backed decision for an assessment turn: next item, retry, or final placement.
- **Assessment Diagnostic Event**: Reviewable record of assessment progress, outcome type, policy enforcement, or provider failure.
- **Observation Span**: Optional runtime trace around state dispatches or user mediation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Validation covers at least five assessment answer patterns, including strong, weak, mixed, contradictory, and unusable answers; each turn after the first uses prior evidence to choose next item, retry, or final placement.
- **SC-002**: No assessment validation case shows more than one unanswered item or bypasses existing minimum-evidence and maximum-item boundaries.
- **SC-003**: Assessment diagnostics are covered for next-question, retry, final-placement, and provider-error outcomes.
- **SC-004**: LLM completion logging is covered for successful structured calls, raw calls, provider options, and provider errors.
- **SC-005**: Observability is covered for disabled tracing, enabled tracing, repeated configuration, explicit disablement, and shutdown behavior.
- **SC-006**: Persisted session validation covers startup recovery and storage round trips for representative active workflow states.
- **SC-007**: Full project QA passes before the feature is merged.

## Assumptions

- Assessment is the first workflow used to evaluate the adaptive framework; curriculum and lesson rework will be specified separately after assessment behavior is reviewed.
- Existing curriculum, lesson, retention, privacy, and provider-interface policies remain in force.
- Diagnostic logs and tracing metadata are intended for development and evaluation, not learner-facing reporting.
- Optional tracing depends on environment configuration and must not be required for local development or tests.
