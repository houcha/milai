# Architecture

`CLI/Web -> Tutor -> OpenAI Agents SDK Runner -> OpenAI Responses API`

Milai has one learner-facing tutor with two conversation scopes in each session:
main chat and one discussion per lesson. The main chat chooses direction and
introduces a generated lesson with a card. Lesson discussions answer questions,
handle submitted answers, and add requested practice. The tutor keeps its chat
model separate from a private lesson planner and exercise reviewer; all share one
authenticated API client and one shutdown path.

## Lesson generation

`start_lesson` supplies the planner with explicit learner goals, evidence,
reusable skills, prerequisite status, validated source excerpts, and a focused
lesson intent. The planner returns a typed draft with one focus skill and its
direct prerequisites, objective, ordered Markdown sections with stable IDs,
worked examples, recap, and three to six exercises. At least two exercises are
unscaffolded. The application resolves skill references, checks ownership,
prerequisite graph integrity, content bounds, and exercise contracts before saving.
The document is capped at 32,000 characters; the generation request allows
32,768 output tokens shared by reasoning and visible output.

Generation uses `OPENAI_LESSON_MODEL=gpt-6.1-sol`,
`OPENAI_LESSON_REASONING_EFFORT=low`, and
`OPENAI_LESSON_SERVICE_TIER=fast` by default. The SDK receives the reasoning
effort and `ModelSettings.extra_body={"service_tier": "fast"}`. Chat, lesson
questions and extra practice retain the configured chat model,
low reasoning, and its existing processing setting. No model or effort fallback
occurs on unsupported configuration, provider errors, or timeouts. A SQLite
transaction covers lesson content, exercises, card linkage, main reply, and the
rest of the turn. Progress stages can be shown while generation runs; only
committed content is exposed as a finished lesson.

A valid draft selecting the already-active skill returns a recoverable
`invalid_operation` before any writes. Requested extra practice uses
`present_exercise` in that existing lesson. It never substitutes practice for
a move-forward request or retries lesson generation in the same turn. Other
invalid generated content and operational failures still roll back the turn.

## Learning state

Each session has a skill graph and a chronological list of generated lessons.
A skill is a language-specific, reusable ability with a definition and observable
success criteria. Directed prerequisite edges must be acyclic. A lesson references
exactly one focus skill. Generating a lesson updates the session's current
teaching focus; viewing an older lesson does not. A later lesson on the same skill
is a separate Review entry. Titles are derived from the skill name, with a
`Review ·` prefix for revisits; an example context or source cannot become the
lesson title. Each session has one language, shown in the browser's path-rail
brand and Sessions list. On narrow screens the language link moves above the
session title; hover and keyboard focus expose its Sessions destination. Session
metadata uses the latest saved target-language
fact, falling back to the first stored lesson's language when no fact is available.
Unknown languages show the default brand word. These labels and titles are derived on read,
including for existing lessons, without a schema change.

Prerequisites inform lesson background without gating progression. Mastery is derived
from two independent successes on distinct unscaffolded exercises since the
latest substantial `needs_work` observation. An independent success has no
skill-specific assistance. A minor slip can count as success while remaining
due for a later check. Reading, navigation, and discussion without an answer
submission create no attempt or mastery evidence. Prepared exercises remain
accessible after a minor slip; automatic new remedial practice waits for the
existing delayed-review rule. An explicit request can bring practice forward.
Assessments record due-review recommendations. Only an explicit continuation
request lets main chat generate the next appropriate lesson, with review optional. Incorrect or incomplete
practice does not block a new focus or mark any prerequisite mastered.

Exercises belong to a lesson, target its focus skill, and may list previously
taught supporting skills, including attempted skills without lesson completion
or mastery. Prompts use evidence to choose suitable difficulty and support and
require supplying incidental vocabulary when familiarity lacks evidence. Grammar
assessment separates such vocabulary gaps from target errors. These teaching
rules remain prompt contracts rather than automatic language analysis.
Attempts and help retain exact exercise and skill
references. Ambiguous requests are clarified before evidence is assigned. Skills
can be superseded without rewriting historical lessons or observations.

### Typed exercises

All new planner and `present_exercise` outputs require a version-1 exercise
contract with one of four content variants: `complete_sentence`,
`translate`, `transform`, or `short_response`. Each has 1–12 items. Shared Python
models validate gap counts and content bounds. The application
compiles a fixed English instruction, title, and readable task; labels such as the
answer language and target form are bounded parameters. Item text and context are
plain content, never a place for additional instructions. Lesson generation still
requires two unscaffolded exercises. A separate stored-contract schema retains
choice support for historical exercises; new writes reject choice contracts.

SQLite retains the private contract alongside the compiled task. Public exercises
add `format` with type, instruction, parameters, and items; an explicit projection
excludes reference answers and choice keys. Only answer turns load the selected
exercise's private `assessment_contract`. Ordinary discussion, public lesson data,
activities, snapshots, and replay do not load private keys.

The browser renders structured items directly, without parsing Markdown lists.
It submits JSON-quoted `Item N:` strings through the existing answer endpoint.
The tutor validates exact item mapping before model execution and normalizes
single-item plain text into that format. Choices submit option numbers. Typed
multi-item terminal answers use `/answer <id>` to collect one answer at a time;
legacy and single-item answers retain `/answer <id> <text>`. Bad mappings are
rejected without consuming a submission.

Typed reviews return `item_results` with one numbered correctness
flag and feedback per item; aggregate score must be null and legacy feedback fields
empty. Storage validates complete coverage, checks choice flags against the saved
key, and rejects correct marks for empty answers. It calculates one point per
correct item. Production assessment accepts alternative correct answers; short
responses are assessed holistically against their visible focus. References cannot
add hidden criteria. The model still records skill observations separately.
Choice accuracy cannot contribute independent mastery evidence.

Typed practice sets expose `scoring: "items"` and show correct answers out of total
answers. Existing component and legacy whole-exercise results retain their labels
and aggregation. Per-item results persist and render next to the saved answer;
only incorrect items get explanatory feedback. Existing draft keys, per-exercise
pending state, final submissions, and transaction rollback remain in use.

### Saved legacy exercise rendering

The following Markdown and scoring behavior applies to existing exercises without
a typed contract; they are neither converted nor rescored automatically.

Exercise tasks remain Markdown strings. The lesson planner and `present_exercise`
can use up to 12 literal `{{blank}}` markers for inline short answers; model
schemas and storage validate their spelling and count. The exercise-only
Markdown renderer emits fixed numbered spans, and the app creates accessible
text inputs with a 200-character limit, associated with one exercise form.
Model HTML stays disabled. Markers inside code, math, or links fall back to
static blanks and the normal free-text form so numbering cannot silently shift.
Multi-part tasks are requested as Markdown lists, with one item per line.

For tasks without explicit blank markers, the exercise renderer annotates each
top-level ordered-list item with a stable number in reading order. The app adds
a wide, underlined textarea below each item; it expands for multiline answers.
Nested lists remain part of their parent prompt. A single form submits all items
together as `Item N: <JSON-quoted text>` lines, preserving embedded newlines and
label-like learner text. Draft arrays use the same session/lesson/exercise key.
Saved answers are decoded and rendered as plain text beneath their items without
a duplicate response block. Existing shared drafts and unmapped historical
responses retain their full text. Inline-marker tasks keep their existing controls
and malformed-marker fallback. This presentation change needs no schema migration;
enumerated answers retain free-text assessment and component scoring.

Inline answer drafts are arrays stored under the existing session/lesson/exercise
key. One `action: answer` request sends all fields as `Blank 1: ...` lines in
reading order; the existing tutor assessment and attempt storage remain in use.
Every saved submission replaces its inputs with the saved answer text, regardless
of correctness. New assessments persist one numbered result per blank, validated
against the task's marker count and aggregate score. Correct fills have no feedback;
incorrect or missing fills have a correction and brief explanation. The browser
colors mapped fills green or red with check/cross marks and accessible labels,
omits the duplicate answer block, and shows only incorrect-fill feedback. All-correct
submissions have no feedback block. Legacy assessments retain their feedback and
neutral fills; terminal or otherwise unmapped answers retain their full response
below the task. A failed transaction keeps the draft available to submit again.
The terminal shows numbered static blanks and retains `/answer`.

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

For legacy exercises, `assess_attempt` requires a score of correct and total requested answer parts
(0–100 correct out of 1–100 total). Storage validates bounds before writing.
The model counts the task's explicit components consistently, independent of the
learner's response. Skill observations and mastery remain separate: a minor slip
can evidence understanding while losing an accuracy point.

Exercises from the same generating turn form one practice set. `practice_results`
on each lesson exposes submission counts and, once the set is finished, its
aggregate accuracy. New sets sum correct/total counts rather than averaging
exercise percentages. A set containing legacy unscored assessments instead counts
fully correct exercises, with an explicit UI label; missing legacy assessments
produce no numeric rate. Integer percentages round down so only perfect work
shows 100%. Results persist through their source records rather than a cached
score. Each later requested set has its own result and suggested review time,
24 hours after its last first submission. Timing is advisory and does not block
practice. Prompts request fresh analogous tasks on demand and no resubmission;
`present_exercise` rejects automatic new practice during an answer turn.

Each practice result also exposes `set_id` (its generating turn), the completing
first-submission `completion_turn_id`, and nullable `completion_summary`. The
assessment tool returns the selected set's computed status and, when finished,
its first-assessment evidence, including the current uncommitted assessment.
The private reviewer receives compact previous assessment evidence only when its
submission will complete the selected practice set. Its structured output may
provide a recap of at most 600 characters. It is
saved on the completing answer turn in the same transaction; non-completing
turns cannot save a recap, and absent recaps do not invalidate assessments.
Later discussion summaries cannot overwrite a set's recap. Existing results
retain their scoring and have no inferred completion prose.

The browser updates the original main-chat lesson card in its introducing
message when results arrive. One card per lesson retains its title and objective,
shows every completed set's score, and offers a single Open lesson or Revisit
lesson navigation action. A standalone card is inserted at the first completion's timestamp only
when no introducing card exists in the loaded history. Cards derive from the
existing learning payload; they are not synthetic conversation turns or
model-history entries. Live updates preserve the card and its containing message,
pending messages, and chat scroll. Unchanged cards retain their controls. Both initial loads
and committed answer responses supply results, with session checks for background
responses. No new endpoint or model call is needed.

New lesson appears after the last lesson in the learning-path sidebar,
hidden when the session has no lesson. It sends explicit main-chat continuation
with the current teaching focus as `origin_lesson_id`; opening an older lesson
does not change that target. The tutor acknowledges results and prepares
the next lesson in that turn. The completion panel's only action is More practice,
which uses an ordinary lesson discussion
request, preserves the unsent draft and quote, and reveals fresh exercises after
they save. Failed actions offer a retry tied to the originating lesson.

## Tutor loop and context

Explicit answer submissions take a separate path after ownership, final-submission,
and item-mapping checks. One tool-free structured Responses request uses
`OPENAI_REVIEW_MODEL=gpt-6-luna`, `OPENAI_REVIEW_REASONING_EFFORT=medium`, Standard
processing (`service_tier="default"`), and
`MILAI_REVIEW_MAX_OUTPUT_TOKENS=8192`. It receives the selected
exercise and private contract, learner answer, relevant skill definitions and
criteria, lesson objective and recap, explanation preferences, skill-specific
assistance flags, and the previous discussion summary. It does not replay the
conversation, full document, source records, skill catalog, or other exercises.
The completing submission additionally receives previous scores, observations,
and incorrect-part feedback from its own practice set.

The review returns the existing assessment schema, public reply, updated summary,
and optional completion recap. A shared persistence function retains the same
score, observation, assistance, review, and mastery validation as the assessment
tool. Assessment, reply, summary, and recap save in one transaction. Invalid
output, timeouts, or provider failures leave the submission available for retry;
there is no automatic retry, model fallback, or subsequent tutor call.
Only the original user message and public reply enter `turns.items`, never the
private review input or structured output envelope. The packaged reviewer prompt
contributes to the combined prompt hash. Existing framework instrumentation
captures the generation; the application span adds reviewer identity, request
count, input/cache-read/cache-write/output/reasoning token counts, and commit IDs
under the same content-privacy settings. All three model adapters share one API
client, closed once.

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

SQLite schema 10 stores nullable `turns.completion_summary`, alongside `exercises.contract` and
`attempts.item_results` JSON. Null contracts identify preserved legacy exercises.
It also stores optional part-level scores and per-blank assessment results
on attempts and selected text alongside each discussion turn, in addition
to lesson documents, scoped references, discussion summaries, current teaching
focus, and presentation links. Schemas 5–9 upgrade transactionally on open,
adding the typed fields after applying earlier steps: add nullable `attempts.blank_results`, add `attempts.score` for schemas 5/6, and add
`turns.selected_text` for schema 5, followed by the nullable completion recap.
Existing data is preserved; historical attempts
keep their existing scores and have no inferred blank results.
Ownership checks and session deletion cover every record. Schemas older than 5
still require `milai reset --yes`, which archives the database and WAL/SHM
sidecars before creating the current schema.

The browser lesson route hides the learning-path rail and session header, using
the full workspace for the document beside its discussion. The lesson's own
heading stays visible; returning to chat restores the rail and header. On narrow
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
stored lessons directly. An accessible back-arrow button covers the full left
reading gutter on desktop, with its arrow centered horizontally and vertically.
Its width follows the actual content edge after rendering and resizing. Wheel
events over this gutter scroll the reading pane with pixel, line, and page
deltas normalized; zoom gestures keep their default behavior. The button sits
beside the existing tabs on narrow screens, without a
toolbar row. A single-finger right swipe also returns to chat at widths up to
850 pixels. Touch listeners recognize a horizontal swipe of at least 80 pixels
within 700 milliseconds; vertical movement, cancellation, multitouch, selected
text, controls, and horizontally scrollable content do not navigate. Native
scrolling is prevented only after recognizing a horizontal rightward drag.
Back navigation retains the teaching focus; the learning path's **New lesson**
shortcut advances from the current
teaching focus. Browser session storage keeps per-session, per-lesson drafts, selected
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
