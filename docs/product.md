# Product brief

Milai is a conversational language tutor that learns what a person wants to do
with a language and adjusts teaching to evidence from their attempts. It asks
about target and explanation languages, experience, goals, interests, and source
preferences; unknowns remain unknown. An initial curriculum is provisional and
high level. Lessons and exercises emerge when useful, and change as evidence grows.

Explanation, practice, hints, clarification, and assessment can occur in any order.
Assisted success is useful evidence, but is never recorded as independent success.
Recurring mistakes inform later teaching without becoming permanent learner labels.
Sources are general-purpose, attributed, and treated as untrusted data. Unavailable
material is reported honestly; original teaching examples are labeled as such.

## Explicit initial decisions

- Python, a local single-user CLI, and SQLite provide the first complete experience.
  The OS account owns the database; no network-facing service or login is implied.
- One conversational OpenAI Agents SDK agent selects teaching actions from versioned
  Markdown procedures; an optional adviser supports deliberate planning. There is
  no onboarding/lesson/assessment state machine.
- Gemini endpoint, model, and key are configuration. The user selected Gemini 3.5
  Flash Lite after NVIDIA inference failed, and confirmed a Free Tier project with
  no billing attached. There is no automatic retry or fallback to another model.
- Public HTTPS text/HTML URLs and pasted text are the initial source formats.
  Retrieval is topic-independent. Search engines, PDF/audio/video extraction,
  paywalls, and authenticated sources are future adapters, not fabricated support.
- Durable profile facts include their supporting learner quote; curricula retain
  revisions. Evidence records learner text, skill, outcome, assistance, and rationale.
- No numeric mastery score is inferred from one answer. Teaching quality is reviewed
  independently of storage, authorization, and runtime tests.
- Langfuse uses its supported OpenInference Agents integration. Local state events
  carry prompt version and provenance. Trace content is hidden by default; synthetic
  acceptance runs can explicitly opt into content for pedagogical review.

## Consequential open questions

1. First delivery: local text chat, confirmed. Browser and hosting remain future work.
2. Gemini 3.5 Flash Lite is selected. Live compatibility remains a verification gate:
   model availability alone does not establish tool calling and continuation.
3. Intended age range, deployment region, retention/deletion policy, and permission
   to capture learner content in tracing must be decided before public deployment.
4. Which non-text sources and discovery/search provider should follow URL retrieval?
5. What languages and learner populations define the first pedagogical evaluation?
   Initial synthetic examples are demonstrations, not evidence of universal quality.

## Acceptance scenario (not a required interaction sequence)

A learner converses about their needs; receives a provisional outline; uses a
retrieved source in a small lesson; tries an exercise; receives feedback and optional
help; and later gets a teaching action justified by persisted evidence. Restart the
application between attempts to demonstrate durable memory. Also exercise a learner
who asks for practice immediately, an unavailable source, and success after a hint.

## Milestones

1. **Contracts and integration spike:** this brief, architecture, endpoint probe
   covering a tool round trip and continuation; initialize Langfuse integration.
2. **Durable first loop:** conversational CLI, versioned teaching procedures,
   learner-scoped tools, transactional storage and inspectable change events.
3. **Grounded adaptive teaching:** safe general retrieval, citations, exercise and
   assistance records, recurring evidence and subsequent adapted action.
4. **Acceptance and handoff:** deterministic behavior tests, live integration report,
   separate tutoring-quality rubric/transcript, runnable documentation and limitations.

Review boundaries follow these milestones; commits are not created automatically.
