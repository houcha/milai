# Product brief

Milai is a conversational language tutor that discovers why a person is learning,
chooses a useful language ability, and teaches it until the learner can apply it.
The learner does not need to choose a curriculum or a specific source to begin.

Each lesson focuses on one new language skill or one previously taught weak skill.
Skills are precise, reusable abilities in grammar, vocabulary, sound, spelling,
or comprehension. A lesson remains active across turns. Future lessons may draw
on earlier skills because complex language use builds on simpler abilities. Each
exercise has one target matching the active lesson; previously taught skills may
be supporting skills. A lesson title is derived from the language and focused
skill, with a Review prefix for revisits.

Prerequisite edges form a directed acyclic graph. Every prerequisite must be
mastered before a new dependent skill is taught. Mastery means two independent
successes on distinct exercises since the most recent `needs_work` observation.
Assisted, scaffolded, or uncertain responses do not count. An advanced request
never bypasses the gate; the tutor explains the prerequisite and teaches the
earliest unmet one. Repeated difficulty, a learner request, or a blocking weak
skill can start a separate review lesson. One error normally stays within the
current lesson.

The tutor explains a coherent system of related forms in enough depth to make it
usable. It supplies examples relevant to the learner's goal and level. An example
may be authentic when confidently recalled, but close reading requires supplied
or retrieved source material. The example does not change the skill focus. Practice
follows sufficient explanation and learner readiness, so many turns have no exercise.

Evidence consists of actual attempts and per-skill observations. Help is attached
to the affected exercise skills. Skills can be superseded without rewriting old
evidence or lesson history. The Skills view shows derived mastery, counts,
assistance, recency, and contexts without a numeric score. The learning path is a
chronological list of lessons that link to their creation turns.

Milai runs locally in terminal or browser, uses the OpenAI Agents SDK and local
SQLite, and keeps one learner-facing agent. A private read-only planner selects
one lesson skill when the focus changes. The application validates the choice,
prerequisites, exercise contracts, ownership, and persistence. A schema change
requires an explicit archival reset; no implicit migration is attempted.

## Open product questions

1. Intended age range, deployment region, retention policy, and tracing consent.
2. Which languages and learner populations define the first teaching evaluation.
3. Which discovery provider and non-text formats should follow URL retrieval.
4. How learners should edit facts or reset part of a session's learning state.
