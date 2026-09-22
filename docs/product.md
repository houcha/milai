# Product brief

Milai is a conversational language tutor that discovers why a person is learning,
builds a minimal model of the language abilities they need, and adjusts teaching to
evidence from their attempts. The tutor asks the intent questions itself; the learner
does not need to request a curriculum or know how to organize the subject.

The organizing model is a reusable skill graph. Skills are precise language abilities,
such as past simple irregular forms, article selection, prepositions, plural formation,
or main-clause word order. Topics describe where those abilities are applied and only
reference skill IDs. Each topic begins with 3–8 vital core skills. Explanations support the
current focus, exercises combine honest sets of target and supporting skills, and the
graph expands as the learner advances. One session-wide focus points to the current
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
  Topic establishment internally invokes a read-only High-reasoning planner with typed
  output; normal conversation uses Low reasoning. The planner is an implementation detail
  of topic creation rather than a second public workflow step. Separate onboarding and
  lesson agents are unnecessary while one active focus and bounded state provide clear
  control.
- The model explains naturally in its persisted conversational response. Exercises use
  structured cards because later assistance and assessment must reference an exact task
  and skill contract.
- Gemini endpoint, model, and key remain configurable. There is no automatic retry or
  provider/model fallback.
- Public HTTPS text/HTML URLs and pasted text are the initial source formats. Search,
  PDF/audio/video extraction, paywalls, and authenticated sources remain unsupported.
- Langfuse uses supported OpenInference Agents instrumentation. Local audit events hold
  prompt version and provenance. Trace content is hidden by default.
- Legacy databases are never silently interpreted. `milai reset --yes` archives the
  previous files and creates the current normalized schema.

## Acceptance behavior

A learner states a language and purpose. Before choosing a first lesson, the tutor
uses saved experience or relevant evidence, or asks a short experience question and
waits. Free-form experience is stored in `level`; CEFR labels are optional. Uncertain
learners can try a diagnostic, and explicit requests to start immediately are honored.
Returning learners do not repeat discovery when useful context exists.

The tutor saves exact facts and privately plans the core graph using the profile and
evidence for reusable skills. Each teaching turn normally introduces one target skill
for one coherent objective, with meaning, a pattern, and a worked example before
manageable practice. The topic inventory is not a checklist for a single reply.
Explanation depth and pace follow experience, observed performance, and feedback.
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

## Session navigation

The interface prioritizes sustained learning within one session. A chronological
chain of topics occupies the left sidebar; clicking a topic revisits its original
discussion without changing focus. Earlier topics are not labeled complete merely
because they are older. Skills is available below the path. Session management lives
in a separate Sessions view reached through the Sessions link, with per-session rename
and delete controls. Conversation and practice use a single main content area.
