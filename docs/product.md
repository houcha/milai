# Product brief

Milai is a conversational language tutor that discovers why a person is learning,
chooses a useful language ability, and teaches it until the learner can apply it.
The main conversation is the home for choosing direction. It introduces a complete
lesson with an **Open lesson** card, then lets the learner return to discuss progress
and choose what comes next. The learner does not need to choose a curriculum or a
specific source to begin.

Each lesson is a fixed document focused on one precise, reusable language skill.
It contains an objective, ordered explanation sections, worked examples, a recap,
and three to six exercises, including at least two without scaffolding. The
lesson's own conversation stays available beside the document. Learners can ask
about a section or exercise, submit an answer, and return later to the same
discussion. Each question considers the complete lesson. Highlighting lesson or
exercise text optionally attaches a removable quote to the next question, without
switching tabs or moving the cursor. The quote clears after a successful send
and stays with that message in conversation history. There are no repeated
section or exercise question buttons. Further explanations appear in discussion;
additional practice is appended to the lesson. The generated-lesson list records history, not a future
roadmap. Reopening a past lesson does not change the current teaching focus.

Prerequisite edges form a directed acyclic graph. Every prerequisite must be
mastered before a new dependent skill is taught. Mastery means two independent
successes on distinct unscaffolded exercises since the latest substantial
`needs_work` observation. Assisted, scaffolded, or uncertain responses do not
count. A mostly correct answer with a minor slip may count as success, with the
slip recorded for a later check. Prepared exercises remain available after such a
slip; newly generated remedial drills wait for the delayed review unless the
learner asks for them. An advanced request never bypasses a prerequisite; the
tutor explains the relationship and teaches the earliest eligible skill.

Short-answer exercises can place editable blanks directly in numbered sentences.
The learner fills them in and submits the exercise once; the tutor assesses all
answers together. Drafts survive reloads and failed submissions. Answers that
need correction remain editable, and completed exercises show submitted words
as text. Open-ended writing keeps a normal answer box. New practice uses separate
numbered lines; saved exercises retain their original format. Submitted answers,
assessment feedback, and answer clarification replies stay on the exercise cards.
The discussion chat displays questions and their replies, including questions
about exercises, without replaying answer submissions.

Each exercise belongs to one lesson and targets that lesson's focus skill.
Previously taught skills may support it. Questions and clarification do not count
as attempts. Help is attached only to the exercise skills it concerns, including
help requested in main chat. Assessments record evidence and may recommend a
review, but do not automatically open a new lesson. The learner can explicitly
continue from an older or current lesson, and main chat chooses the next eligible
lesson or review. Progress is derived from recorded attempts rather than a
numeric score.

The shared learning profile records explicit goals, interests, source preferences,
and quoted teaching preferences within the current session. A lesson discussion
keeps a short summary of unresolved questions and requested next steps so it
remains useful after long conversations and restarts. The main chat can retrieve a
bounded portion of a lesson's document or discussion when needed. Sources may be
learner-supplied or retrieved from a public HTTPS URL. Original examples are
distinguished from verified source excerpts.

Milai runs locally in terminal or browser, uses the OpenAI Agents SDK and SQLite,
and keeps one learner-facing tutor. Chat and assessment use the configured
`OPENAI_MODEL` with low reasoning. A private structured planner uses the separate
lesson model and generation settings; the application validates its draft before
saving the document, exercises, lesson card, and main reply together. A failed
generation leaves the turn unchanged. Schema 5 databases upgrade to schema 6
without losing saved lessons or conversations. Earlier schemas require an explicit
`milai reset --yes` archival reset.

## Open product questions

1. Intended age range, deployment region, retention policy, and tracing consent.
2. Which languages and learner populations define the first teaching evaluation.
3. Which discovery provider and non-text formats should follow URL retrieval.
4. How learners should edit facts or reset part of a session's learning state.
