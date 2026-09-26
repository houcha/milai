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

Exercise tasks remain Markdown strings. The lesson planner and `present_exercise`
can use up to 12 literal `{{blank}}` markers for inline short answers; model
schemas and storage validate their spelling and count. The exercise-only
Markdown renderer emits fixed numbered spans, and the app creates accessible
text inputs with a 200-character limit, associated with one exercise form.
Model HTML stays disabled. Markers inside code, math, or links fall back to
static blanks and the normal free-text form so numbering cannot silently shift.
Multi-part tasks are requested as Markdown lists, with one item per line.

Inline answer drafts are arrays stored under the existing session/lesson/exercise
key. One `action: answer` request sends all fields as `Blank 1: ...` lines in
reading order; the existing tutor assessment and attempt storage remain in use.
Every saved submission replaces its inputs with the saved answer text, regardless
of correctness. A failed transaction keeps the draft available to submit again. The terminal
shows numbered static blanks and retains `/answer`. Existing tasks are unchanged;
this Markdown extension requires no database migration.

The browser excludes `action: answer` turns from the visible discussion, both
while submitting and when replaying saved history. Answer progress and failures
appear on the exercise card; submitting does not scroll or add messages to the
discussion. Assessment status includes its `turn_id` so the card can associate
feedback with a submission without duplication. Answer turns without a recorded
assessment still show their clarification reply on the card. All turns remain
persisted and available to tutor history and learning evidence; ordinary
questions about exercises remain visible in discussion.

Answer requests use per-session, per-lesson, per-exercise pending state instead
of the browser's global busy flag. Only the submitted exercise is disabled;
duplicate submissions are ignored while it is pending. Completion clears the
originating draft and updates only that card if its lesson is still visible.
Other drafts, text selection, discussion messages, and focused fields remain
untouched. Pending progress survives navigation within the page; failures remain
on the owning card and unlock it for retry. Tutor writes still run serially.
Lesson and bootstrap GETs use short-lived read-only SQLite snapshots of committed
state, outside the model-turn lock. Read transactions close before sending the
HTTP response, so navigation neither waits for model execution nor exposes its
uncommitted changes.

## Final submissions and practice results

An exercise permits one saved answer. Both the tutor's preflight check and the
assessment store reject another submission, independently of correctness. Answer
turns must record an assessment before committing; absent assessments roll back
instead of consuming the submission. `completed` and `submitted` mean final,
while `correct` reflects the first assessment's accuracy. Historical attempts
remain readable; later corrections do not improve a first-submission result.

`assess_attempt` requires a score of correct and total requested answer parts
(0–100 correct out of 1–100 total). Storage validates bounds before writing.
The model counts the task's explicit components consistently, independent of the
learner's response. Skill observations and mastery remain separate: a minor slip
can evidence understanding while losing an accuracy point.

Exercises from the same generating turn form one practice set. `practice_results`
on each lesson exposes submission counts and, once the set is finished, its
aggregate accuracy. New sets sum correct/total parts rather than averaging
exercise percentages. A set containing legacy unscored assessments instead counts
fully correct exercises, with an explicit UI label; missing legacy assessments
produce no numeric rate. Integer percentages round down so only perfect work
shows 100%. Results persist through their source records rather than a cached
score. Each later requested set has its own result and suggested review time,
24 hours after its last first submission. Timing is advisory and does not block
practice. Prompts request fresh analogous tasks on demand and no resubmission;
`present_exercise` rejects automatic new practice during an answer turn.

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
outside the shared-state budget, a rolling discussion summary, optional selected
text and its section or exercise reference, and relevant shared learning state.
Quotes are learner-provided context, not instructions or verified source material.
They accompany their own turn in bounded replay and discussion retrieval rather
than establishing a persistent focus. Lesson turns produce a
structured learner-facing reply and an updated summary of at most 2,000
characters. Both save atomically, with the updating turn recorded. Summaries
retain unresolved questions and requested next steps. Persistent goals and
preferences require explicit learner statements; `teaching_preferences` stores
their quote.

## Storage and navigation

SQLite schema 7 stores optional part-level scores on attempts and selected text
alongside each discussion turn, in addition
to lesson documents, scoped references, discussion summaries, current teaching
focus, and presentation links. Schemas 5 and 6 upgrade transactionally on open: add nullable `attempts.score`,
and add `turns.selected_text` when upgrading from schema 5. Existing data is
preserved; historical attempts keep a null score.
Ownership checks and session deletion cover every record. Schemas older than 5
still require `milai reset --yes`, which archives the database and WAL/SHM
sidecars before creating the current schema.

The browser lesson route shows the document beside its discussion. On narrow
screens, **Lesson** and **Discussion** tabs replace the columns. Exercises appear
under the explanation, with status and answer fields. Submitted exercises retain
past answers and feedback without answer controls. There are no section or
exercise question buttons: selecting reading text automatically attaches a
removable plain-text quote beside the composer without changing focus or tabs.
The browser identifies its section, worked example, or exercise when both ends
belong to the same item; cross-section selections remain lesson-wide. Quotes
are limited to 4,000 characters; longer selections show a shortening request.
Chat requests accept optional `selected_text` only for lesson discussion messages,
alongside existing optional `section_id` or `exercise_id`. The HTTP body limit is
64 KiB. The full lesson remains available whether or not a quote is attached.
Cards and sidebar entries open
stored lessons directly. **Back to conversation** navigates without changing
focus; **Continue learning** sends a main-chat continuation tied to its origin
lesson. Browser session storage keeps per-session, per-lesson drafts, selected
text, and reading position through reloads and clears them on session delete.
Legacy browser references without quotes are discarded while preserving other
draft state. The pending quote clears after a discussion turn commits, remains
after failure, and is never included in answer submissions. Saved quotes appear
with learner messages on reload. Answering an exercise does not set discussion focus.
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
