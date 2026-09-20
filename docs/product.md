# Product brief

Milai is a conversational language tutor that discovers why a person is learning,
builds a minimal model of the language abilities they need, and adjusts teaching to
evidence from their attempts. The tutor asks the intent questions itself; the learner
does not need to request a curriculum or know how to organize the subject.

The organizing model is a reusable skill graph. Skills are precise language abilities,
such as past simple irregular forms, article selection, prepositions, plural formation,
or main-clause word order. Topics describe where those abilities are applied and only
reference skill IDs. Each topic begins with 3–8 vital core skills. Theory supports the
current focus, exercises combine honest sets of target and supporting skills, and the
graph expands as the learner advances. One learner-wide focus points to the current
topic and skills while remaining able to move when intent drifts.

Evidence consists of real attempts and per-skill observations. Assistance is attached
to the affected exercise skills. Assisted success is useful, but cannot count as
independent success; a fresh task checks transfer. The product shows counts, recency,
contexts, and observed outcomes without assigning a mastery stage or numeric score.
Skill definitions can split, merge, or improve without rewriting old evidence.

## Initial product decisions

- Python, local CLI/web interfaces, and SQLite provide the complete local experience.
  The OS account is the authorization boundary; no hosted service or login is implied.
- One conversational OpenAI Agents SDK agent owns the relationship and teaching loop.
  A mandatory read-only High-reasoning planner decomposes each new topic once; normal
  conversation uses Low reasoning. Separate onboarding and lesson agents are unnecessary
  while one active focus and bounded state provide clear control.
- The application renders persisted theory and exercise cards. The model's final prose
  frames these artifacts rather than retyping them, so what the learner sees has an
  exact durable record.
- Gemini endpoint, model, and key remain configurable. There is no automatic retry or
  provider/model fallback.
- Public HTTPS text/HTML URLs and pasted text are the initial source formats. Search,
  PDF/audio/video extraction, paywalls, and authenticated sources remain unsupported.
- Langfuse uses supported OpenInference Agents instrumentation. Local audit events hold
  prompt version and provenance. Trace content is hidden by default.
- Legacy databases are never silently interpreted. `milai reset --yes` archives the
  previous files and creates the current normalized schema.

## Acceptance behavior

A learner states a language and purpose. The tutor asks for missing intent, saves exact
facts, reuses any matching skill definitions, privately derives the minimum core graph,
and establishes an initial focus. It gives a theory card and a multi-skill exercise.
On a later turn it records the actual response and per-skill observations, records help
when requested, and offers a fresh transfer exercise. After restart it reconstructs the
focus and evidence from SQLite without replaying full tool traffic or source bodies.

Additional cases cover changed goals, topic switching, skill reuse across topics,
ambiguous answers, repeated errors, unavailable sources, skill redefinition, and
independent transfer after assistance. Structural persistence tests remain separate
from human review of teaching accuracy and naturalness.

## Open product questions

1. Intended age range, deployment region, retention/deletion policy, and permission to
   capture learner content in tracing must be decided before public deployment.
2. Which languages and learner populations define the first pedagogical evaluation?
3. Which discovery provider and non-text source formats should follow URL retrieval?
4. How should learners edit facts, archive topics, or deliberately reset only part of
   their learning state?
