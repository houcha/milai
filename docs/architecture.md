# Architecture

`CLI/Web -> Tutor -> OpenAI Agents SDK Runner -> OpenAI Responses API`

Milai has one learner-facing tutor. The tutor discovers intent, explains, exercises,
assesses, and adapts. `start_lesson` invokes a private read-only structured planner
when the focused skill changes. The application validates and persists the result
atomically. The planner has no write authority or learner-facing reply.

## Learning state

Each session has a skill graph and a chronological lesson list. A skill is a
language-specific, reusable ability with a definition and observable success
criteria. Directed prerequisite edges must be acyclic. A lesson references exactly
one focus skill. The latest lesson is active until a new lesson is created. Repeating
a focus skill creates a new Review entry while preserving the earlier entry. Titles
are derived from language and skill, so a context or source cannot become a lesson
title.

New skills can be taught only after every ancestor prerequisite is mastered. Mastery
is derived from observations: two independent successes on distinct exercises since
the latest substantial `needs_work`. An independent success requires an unscaffolded
exercise and no skill-specific assistance. A mostly correct response with a minor
slip can count as success while retaining its severity for a later check. `uncertain`
and assisted success do not count.
The gate is checked in storage, including when a learner requests advanced material.
The planner selects the earliest eligible prerequisite when needed.
Two consecutive `needs_work` observations on distinct exercises flag an earlier
active skill for review. A minor slip on a previous skill becomes due after two
distinct exercises targeting other skills; its automatic Review waits until the
current skill is mastered. Assessment atomically opens a due Review lesson and
returns it to the tutor for learner-facing explanation. Until that point,
an immediate repeat of the same skill is rejected unless the learner explicitly
requests it.

An exercise belongs to the active lesson and has exactly one target skill, the
lesson focus. Supporting skills must have appeared in earlier lessons and use the
same language. Observations, assistance, and attempts keep their skill IDs. Skill
supersession preserves historical lessons and evidence; the next lesson can use a
replacement skill. Progress summaries remain derived from evidence.

## Tutor loop and tools

One `Tutor.respond` call is one learner turn. The Runner can make multiple model
calls and tool calls before final prose. Local writes are serialized with
`ToolExecutionConfig(max_function_tool_concurrency=1)`. A SQLite transaction wraps
the full turn; per-tool savepoints make correctable validation failures no-write.
The final reply and structured exercises commit together.

The stable tool inventory covers profile facts, skill search, `start_lesson`, skill
supersession, exercise presentation, assistance, attempt assessment, bounded recall,
and source handling. `start_lesson` takes lesson intent, derives target language from
saved facts, and gives the planner the profile, learner message, active lesson,
reusable skills, prerequisite mastery, and evidence. Its typed output selects one
existing skill key or one new skill specification with direct prerequisites. Storage
checks ownership, duplicates, language, DAG constraints, and prerequisite mastery.
The learner-facing tutor explains any prerequisite detour in plain language.

The tutor receives up to six learner-facing turns or 20,000 characters of replay.
Dynamic learning state is capped at 16,000 characters and includes profile, active
lesson, recent lessons, skill catalog and mastery, active exercise, recent focus
evidence, and source metadata. Full source bodies and raw tool traffic are excluded.
The tutor requests bounded source excerpts when needed. Web chat streams provisional
planner and reply text; only the committed response replaces the draft.

The browser opens a presented task through **Start exercise**. Answer turns carry
selected exercise ID as application context. Questions without assessment stay
clarifications. A successful latest assessment closes the task. Continue returns
to conversation after an answered turn without recording assistance. Exercise
status is rebuilt from attempts and assistance after reload.

## Storage and navigation

SQLite schema 4 has normalized tables for sessions, turns, events, facts, sources,
skills, prerequisites, supersessions, lessons, exercises, exercise skills and sources,
assistance, attempts, observations, and ordered turn exercises. Opaque IDs are
checked against the session's learning scope. The model cannot choose a learner,
session, database, or event provenance. Opening an older schema fails with an
explicit `milai reset --yes` instruction. Reset archives the database and WAL/SHM
sidecars before creating fresh schema 4. Existing schema 4 databases gain an
additive `issue_severity` observation column on open; old observations retain their
original outcome and have no retrospective severity.

The lesson sidebar is chronological; its latest entry is current. Clicking a lesson
jumps to its original committed assistant turn without changing focus. Session-scoped
`lesson_anchors` derive those links from audit events joined to committed turns.
Sessions own create, select, rename, and delete controls. Deleting one session's
learning state leaves other sessions intact.

## Sources and observability

Retrieval accepts learner-supplied or saved public HTTPS URLs, uses bounded reads
and timeouts, pins public DNS addresses, and disallows redirects. Source text is
untrusted data. Langfuse's Agents instrumentation exports framework spans; Milai
adds one turn span with pseudonymous IDs, prompt hash, and committed event IDs.
Content is masked by default unless `MILAI_TRACE_CONTENT=true`. Responses use
`store=false` with encrypted reasoning items for tool continuation. Each model
request and tutor turn has a 300-second timeout; failed turns roll back learning
writes and transcript together.
