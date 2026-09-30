# Product brief

Milai is a conversational language tutor that discovers why a person is learning,
chooses a useful language ability, and teaches it until the learner can apply it.
The main conversation is the home for choosing direction. It introduces a complete
lesson with an **Open lesson** card, then lets the learner return to discuss progress
and choose what comes next. The learner does not need to choose a curriculum or a
specific source to begin.

Each session is for one language. Its language replaces the brand word in the
learning-path rail. Hovering or focusing that link reveals **← Sessions**; on
touch screens the language link remains visible with a back arrow above the
session name. Before the language is known, the brand word remains **milai**.
The Sessions list also shows language as secondary text. Lesson headings, cards,
and learning-path entries use only the skill name; revisits keep a **Review ·**
prefix.

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
Lesson view fills the workspace without the learning-path sidebar or session
header. It keeps the lesson heading and makes the full left reading gutter a
back-navigation target, with a small arrow centered inside it and no toolbar
row. Scrolling over that gutter scrolls the lesson. On narrow screens the arrow
sits beside the existing tabs; a deliberate right swipe on reading or discussion content also
returns to the main conversation. Scrolling, text selection, answer controls,
and horizontally scrollable content retain their normal interactions.
Returning to the main conversation restores the sidebar and session header,
with the learning path highlighting the current teaching focus.

Learning-path circles show lesson status: a green checkmark when the original
practice set is submitted, a green ring with a dot for the current unfinished
lesson or one with partial submissions, and a muted empty circle otherwise.
Completion is independent of accuracy and mastery; optional extra practice does
not remove the checkmark. The most recent scored, finished set appears below the
title as a slim green accuracy bar with a right-aligned percentage. Hover text
and accessible lesson labels identify status and practice accuracy. Navigation
highlighting remains separate from these progress indicators.

Prerequisite edges form a directed acyclic graph. Prerequisites guide background
explanations and never block progression. Mastery means two independent
successes on distinct unscaffolded exercises since the latest substantial
`needs_work` observation. Assisted, scaffolded, or uncertain responses do not
count. A mostly correct answer with a minor slip may count as success, with the
slip recorded for a later check. Prepared exercises remain available after such a
slip; newly generated remedial drills wait for the delayed review unless the
learner asks for them. An advanced request can proceed with
necessary background explained inside the new lesson. Explicit requests to move
forward choose another appropriate skill even after incorrect or incomplete
practice; remedial lessons are not compulsory.

New exercises use four consistent formats: complete a sentence,
translate, transform a sentence, and write a short response. The application owns
the English instructions and answer controls; the tutor supplies plain-text items,
necessary context, and private grading references. Each numbered item requests one
answer and earns one point. A translation asks only for the translation, never a
repetition of its source or an additional explanation. All assessed requirements
are visible. Short writing earns a holistic point for the displayed language focus;
valid alternatives are accepted and unrelated mistakes are not penalized.

Sentence completion uses an inline input, and the other
formats use an expanding answer field per item. Each exercise has one submission.
Drafts survive reloads and failed submissions. Submitted answers appear in place
with accessible correct/incorrect indicators; only incorrect answers get a brief
correction or example and explanation. Previously saved choice exercises remain
available with radio buttons; no new choice exercises are generated. Their scores cannot
provide independent mastery evidence. Difficulty also depends on content and
other clues; it is not fixed by the type.

Saved legacy exercises keep their original tasks, answer controls, component scores,
and feedback. They are never automatically converted or rescored. Fresh practice
in an older lesson uses typed exercises and preserves the original set's result.
Answer submissions and assessments stay on exercise cards; questions remain in the
lesson discussion. Browser and terminal support the same formats; `/answer <id>`
collects typed answers item by item in the terminal.
Checking an answer disables only that exercise's answer controls. Learners can
keep reading, navigate between lessons, draft questions, and work on or submit
other exercises while feedback is pending. Feedback updates its own card without
replacing other answer fields or moving focus.

Each exercise belongs to one lesson and targets that lesson's focus skill.
Supporting grammar comes from previously taught or attempted skills; the current
lesson's explicitly explained target is the new grammar to practice. Earlier
lessons need not be fully submitted, correct, or mastered before their grammar
can be reused. Evidence guides difficulty and support rather than eligibility.
Incidental constructions and words in examples do not establish learned skills
or vocabulary. Grammar practice supplies unfamiliar vocabulary and meanings when
familiarity is uncertain, without revealing the tested grammar. A vocabulary gap
or unrelated spelling error does not lose grammar credit when the answer
demonstrates the target; insufficient grammar evidence remains uncertain.
Questions and clarification do not count
as attempts. Help is attached only to the exercise skills it concerns, including
help requested in main chat. Assessments record evidence and may recommend a
review, but do not automatically open a new lesson. The learner can explicitly
continue from an older or current lesson, and main chat chooses the next appropriate
lesson, or a review when requested. Mastery remains derived from skill evidence. Separately, a
practice set shows its correct rate once all its exercises have been submitted.
New typed assessments count correct answers, with one point per item;
legacy tasks retain their explicitly requested component scores, with partial credit;
older sets without part counts show a labelled rate of fully correct exercises.
The lesson list shows the latest scored, finished set's result. Learners can
revisit lessons below 100% and ask for fresh exercises: each generated set keeps
its own result, so a later success does not overwrite the original answers. A review is suggested one
day after finishing a set. This timing is advisory; reading, discussion, and an
explicit request for earlier fresh practice remain available.

Finishing a practice set leaves the learner on the lesson with a completion
panel: its score, a short tutor recap when available, and **More practice** as its
only action. More practice requests fresh exercises in the same lesson and reveals them when
ready, preserving any unsent question and selected quote. The review date is
advisory. Accuracy and mastery remain distinct.

Main chat shows one card per lesson in its introducing message. On completion,
that card keeps the title and objective and changes from **Lesson ready** to
**Lesson complete**, with its score and **Revisit lesson**. Unfinished lesson
cards offer **Open lesson**. Each card has only this navigation action.
Later practice-set results appear in the same card, each with its own label.
Cards survive reloads and also work for historical results; a single standalone
card is used if the introducing message is unavailable. Cards use saved
results; new recaps come from the final assessment turn, without a separate model
request. Older results without recaps retain their scores without an invented
interpretation. Answer submissions and detailed feedback stay on exercise cards.

**New lesson** follows the last lesson in the learning-path sidebar,
using the same gap as other entries and a dotted connector from the last lesson
to its plus marker. It is available once the session has a lesson and advances
from the current teaching focus, including when the learner has revisited an older
lesson. The tutor
acknowledges available results and prepares the next appropriate lesson without
another confirmation. The shortcut preserves an unsent message and is disabled
while a request is pending. Lesson pages have no New lesson action.

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
generation leaves the turn unchanged. Schema 5–9 databases upgrade to schema 10
without losing saved lessons or conversations. Earlier schemas require an explicit
`milai reset --yes` archival reset.

## Open product questions

1. Intended age range, deployment region, retention policy, and tracing consent.
2. Which languages and learner populations define the first teaching evaluation.
3. Which discovery provider and non-text formats should follow URL retrieval.
4. How learners should edit facts or reset part of a session's learning state.
