# Architecture

`CLI/Web -> Tutor -> OpenAI Agents SDK Runner -> OpenAI Responses API`

Milai has one learner-facing tutor with two conversation scopes in each session:
main chat and one discussion per lesson. The main chat chooses direction and
introduces a generated lesson with a card. Lesson discussions answer questions,
assess submitted answers, and add requested practice. The tutor keeps its chat
model separate from a private structured lesson planner; both share one
authenticated API client and one shutdown path.

## Lesson generation

`start_lesson` supplies the planner with explicit learner goals, evidence,
reusable skills, prerequisite status, validated source excerpts, and a focused
lesson intent. The planner returns a typed draft with one focus skill and its
direct prerequisites, objective, ordered Markdown sections with stable IDs,
worked examples, recap, and three to six exercises. At least two exercises are
unscaffolded. The application resolves skill references, checks ownership,
prerequisite mastery, content bounds, and exercise contracts before saving.
The document is capped at 32,000 characters; the generation request allows
32,768 output tokens shared by reasoning and visible output.

Generation uses `OPENAI_LESSON_MODEL=gpt-6-sol`,
`OPENAI_LESSON_REASONING_EFFORT=low`, and
`OPENAI_LESSON_SERVICE_TIER=fast` by default. The SDK receives the reasoning
effort and `ModelSettings.extra_body={"service_tier": "fast"}`. Chat, lesson
questions, assessments, and extra practice retain the configured chat model,
low reasoning, and its existing processing setting. No model or effort fallback
occurs on unsupported configuration, provider errors, or timeouts. A SQLite
transaction covers lesson content, exercises, card linkage, main reply, and the
rest of the turn. Progress stages can be shown while generation runs; only
committed content is exposed as a finished lesson.

## Learning state

Each session has a skill graph and a chronological list of generated lessons.
A skill is a language-specific, reusable ability with a definition and observable
success criteria. Directed prerequisite edges must be acyclic. A lesson references
exactly one focus skill. Generating a lesson updates the session's current
teaching focus; viewing an older lesson does not. A later lesson on the same skill
is a separate Review entry. Titles are derived from language and skill, so an
example context or source cannot become the lesson title.

New skills require every ancestor prerequisite to be mastered. Mastery is derived
from two independent successes on distinct unscaffolded exercises since the
latest substantial `needs_work` observation. An independent success has no
skill-specific assistance. A minor slip can count as success while remaining
due for a later check. Reading, navigation, and discussion without an answer
submission create no attempt or mastery evidence. Prepared exercises remain
accessible after a minor slip; automatic new remedial practice waits for the
existing delayed-review rule. An explicit request can bring practice forward.
Assessments record due-review recommendations. Only an explicit continuation
request lets main chat generate the next eligible lesson or review.

Exercises belong to a lesson, target its focus skill, and may list previously
taught supporting skills. Attempts and help retain exact exercise and skill
references. Ambiguous requests are clarified before evidence is assigned. Skills
can be superseded without rewriting historical lessons or observations.

## Tutor loop and context

One `Tutor.respond` call is one learner turn. The application validates the
session, lesson, section, and exercise relationship before model execution and
distinguishes a question from an answer submission. The Runner can make several
model and tool calls. Local writes are serialized with
`ToolExecutionConfig(max_function_tool_concurrency=1)`. A SQLite transaction
wraps the turn; per-tool savepoints keep correctable validation failures free of
partial writes. The model cannot choose ownership or event provenance.

Main replay contains only main conversation turns. It includes the session's
shared profile and evidence, lesson summaries, review recommendations, and
bounded retrieval of a selected lesson's document or discussion. Lesson replay
contains only that lesson's bounded local history, its complete document loaded
outside the shared-state budget, a rolling discussion summary, the selected
section or exercise, and relevant shared learning state. Lesson turns produce a
structured learner-facing reply and an updated summary of at most 2,000
characters. Both save atomically, with the updating turn recorded. Summaries
retain unresolved questions and requested next steps. Persistent goals and
preferences require explicit learner statements; `teaching_preferences` stores
their quote.

## Storage and navigation

SQLite schema 5 adds fixed lesson documents, scoped turns and references,
discussion summaries, current teaching focus, and turn-to-lesson presentation
links. Ownership checks and session deletion cover every record. Older schemas
fail on open with an explicit `milai reset --yes` instruction; reset archives the
database and WAL/SHM sidecars before creating fresh schema 5.

The browser lesson route shows the document beside its discussion. On narrow
screens, **Lesson** and **Discussion** tabs replace the columns. Exercises appear
under the explanation, with status, answer fields, and **Ask about this exercise**.
Sections have stable **Ask about this section** references. The selected reference
appears beside the composer and can be removed. Cards and sidebar entries open
stored lessons directly. **Back to conversation** navigates without changing
focus; **Continue learning** sends a main-chat continuation tied to its origin
lesson. Browser session storage keeps per-session, per-lesson drafts, selected
exercise, and reading position through reloads and clears them on session delete.
The terminal mirrors navigation with `/lessons`, `/lesson <id>`, `/back`, and
`/answer <exercise-id> <text>`.

## Sources and observability

Retrieval accepts learner-supplied or saved public HTTPS URLs, uses bounded reads
and timeouts, pins public DNS addresses, and disallows redirects. Source text is
untrusted data. Langfuse's Agents instrumentation exports framework spans; Milai
adds one turn span with pseudonymous IDs, prompt hash, and committed event IDs.
Content is masked by default unless `MILAI_TRACE_CONTENT=true`. Responses use
`store=false` with encrypted reasoning items for tool continuation. Model
requests and tutor turns keep their existing 300-second timeout and no-retry
behavior. A failed turn rolls back learning changes and transcript together.
