# Validation: behavior and teaching are separate

## Application behavior (deterministic, offline)

`uv run pytest` uses mocked model and retrieval responses while exercising the
Agents Runner, tool schemas, Responses adapter, SQLite, and instrumentation.
Contract tests cover independent model settings, complete generation, validation
and rollback, scoped replay and ownership, summary updates, evidence, restart,
and session deletion. Browser tests cover direct card navigation, section and
exercise references, answer submission, session switching, and restored drafts.
These tests do not establish tutoring quality.

## Live integrations

`uv run milai probe` checks the configured chat model's tool use and replay, then
checks the configured lesson model (now Sol) with `low` reasoning, Fast mode,
and structured output. Record the returned processing tier when the API supplies it; requesting
Fast does not guarantee that every response uses it. Run this before the learning
scenario. A configured Langfuse client does not by itself prove server ingestion.

`uv run python -m milai.acceptance` asks for a complete lesson, opens a section and
an exercise in its discussion, submits an answer, continues in main chat, then
reopens SQLite and asks another lesson question. It prints transcript, trace IDs,
model compatibility, application checks, and state; `--report PATH` saves JSON.
`--pause` adds a delay between turns if needed. This live run uses paid capacity
and no provider fallback. Its concrete English request is a test fixture, not a
production prompt or teaching sequence. Contract success does not establish
teaching quality; review the transcript separately.

## Tutoring quality review

Score each item 0 (fails), 1 (partial), or 2 (clear success). Cite transcript turns.
No overall pass if source honesty or assistance distinction scores zero.

| Dimension | What a reviewer should look for |
| --- | --- |
| Discovery | Asks about unknown experience before teaching; accepts uncertainty and shortcuts; avoids repeated onboarding |
| Intent | Tutor elicits purpose instead of waiting for a curriculum request |
| Lesson skill | One precise language ability is the new focus; the lesson title names that skill |
| Document | Objective, ordered explanation, worked examples, recap, and exercises form a coherent complete lesson |
| Focus | Reopening an older lesson preserves the current teaching focus; examples do not change it |
| Source honesty | Actual retrieved material, accurate attribution, honest failures |
| Language accuracy | Correct explanation, accepts valid variants, suitable level |
| Interaction | Prepared exercises are appropriate after a complete explanation; questions receive local context without rewriting the document |
| Feedback | Specific, actionable, respectful; separates correct and incorrect components, counts requested parts consistently, and never asks for corrections to a submitted exercise; does not assess questions as attempts |
| Assistance | A helped retry is not called independent mastery |
| Adaptation | Due reviews are optional; explicit continuation selects another appropriate skill with necessary background |
| Memory | Restart preserves useful facts, the lesson document, local discussion, and unresolved questions |

Also manually exercise: proactive intent discovery; the same skill reused in a review
lesson; a changed goal; an ambiguous answer; repeated errors; an advanced request
with unmet prerequisites; help on one skill; independent transfer; a hostile source;
an unavailable URL; and a skill redefinition.
Keep model, prompt hash, transcript, reviewer notes and unresolved defects with each
run. Passing one synthetic English scenario does not establish general language quality.

## Calibration and coherence review

Review these synthetic conversations with the current model and prompt hash. Record
transcripts and reviewer findings; mocked planner tests verify context delivery only.
The first [live complete-lesson run](teaching-review.md) has been reviewed;
broader calibration across the scenarios below remains pending.

| Scenario | Expected behavior |
| --- | --- |
| A language and learning goal, with no prior evidence | Ask about experience and wait before selecting lesson content |
| Same goal, "starting from scratch" | Save the reported level; generate one accessible, complete lesson with meaning, patterns, examples, recap, and prepared practice |
| Same goal, "comfortable reading German novels" | Use an appropriate challenge without automatically reteaching elementary grammar |
| "I'm not sure of my level" | Offer a small diagnostic instead of repeating the level question |
| Returning learner with relevant saved evidence | Use that evidence and avoid repeated onboarding; distinguish assisted from independent success |
| "Skip the questions; give me something to try" | Generate manageable practice and adapt from the response without unnecessary onboarding |
| "Explain more slowly" or "I know this; move faster" | Adjust depth and pace while retaining a clear objective |
| Beginner asks for all German subject pronouns before practice | Cover ich, du, er, sie, es, wir, ihr, sie, Sie with meanings and contrasting examples before the prepared exercises |
| Learner wants to learn German through Rammstein, is starting from scratch, and has no song in mind | Choose a short, accessible title or confidently known phrase to anchor one useful objective; develop that objective before moving to other grammar or pronunciation, and do not ask them to pick a song before teaching |
| After a brief title illustrating a pronoun, the learner needs the pronoun system | Explain the useful pronoun set, meanings, and key contrasts before exploring the title's verb form, pronunciation, or another title |
| Learner supplies a short passage from "Deutschland" and asks for analysis | Identify the pronouns actually present, explain their referents and verb forms, and distinguish original examples from quoted material; do not force an attempt |
| Learner is interested in a different language through books, films, or music but names no work | Choose a suitable brief example within that interest; request a passage only for close reading or uncertain wording |
| Learner wants everyday conversation and mentions no source material | Teach with concrete original examples; do not introduce books, films, music, or source requests |

Check that every lesson and exercise has exactly one target skill.
Review language accuracy separately: explanations must state when a pattern applies
and distinguish general rules from exceptions. Original examples must not be presented
as quotations from source material, and recalled phrases must not be presented as
verified excerpts. Unknown source material must not be invented.

## Lesson progression checks

| Scenario | Expected behavior |
| --- | --- |
| Beginner asks for an advanced construction with unmastered prerequisites | Tutor teaches the requested construction with necessary background; unmastered prerequisites do not block it |
| German pronouns: learner answers four of five correctly but uses `es` for a sister instead of `sie` | Tutor records a minor slip if warranted and corrects briefly; prepared exercises remain available, while new remedial drills wait for later review unless requested |
| Substantial misunderstanding on the current skill | Tutor records difficulty and gives focused teaching |
| Repeated difficulty on a previously taught skill | A due-review recommendation appears; explicit continuation may create a separate Review lesson while preserving history |
| Low score or incomplete practice, then “Let’s move forward” | Tutor starts another appropriate skill, preserves scores and mastery evidence, and does not force remediation |
| Two independent successes on distinct unscaffolded exercises | Skill becomes mastered unless a later `needs_work` observation resets the count |
| An assisted or scaffolded success | Evidence is saved but does not advance mastery |
| A later lesson uses an earlier skill | Exercise targets the current new skill and tags the earlier skill as supporting |

## Conversation and navigation checks

| Scenario | Expected behavior |
| --- | --- |
| Ask about a section, then an exercise | Each question appears only in that lesson discussion with the selected reference and updates its bounded summary |
| Ask what a completed exercise means | Tutor explains it without treating the question as a second answer attempt |
| Ask for help on an exercise in main chat | Assistance is attributed to that exercise's actual skills after any ambiguous reference is resolved |
| Submit an answer to an older lesson's exercise | Assessment uses the selected lesson and exercise, even if a newer lesson is the current teaching focus |
| Reopen an older lesson and return to main chat | Focus and evidence stay unchanged; a continuation request can carry the origin lesson |
| Restart and switch sessions | Lesson documents, summaries, and drafts stay with their owning session; cross-session IDs fail before the model call |

## Final-answer scoring scenarios

Review live outputs for these synthetic cases; deterministic tests establish
storage and display contracts, not grading quality.

- For typed translation, provide “You have” with informal plural context. Submit
  “ihr habt” alone and expect 1/1, without repeating the source meaning.
- Generate samples of all four current types. Check plain factual cues,
  references that satisfy the visible task, and absence of extra instructions in
  content. For translation and writing, try a correct answer absent from references.
- For saved legacy tasks only, preserve multi-component grading: four forms and
  four requested meanings still total eight parts. Never rewrite or rescore history.
- For an open-ended task requiring one sentence, accept valid alternatives and
  count one answer. Assess the visible focus holistically, and do not invent extra
  grading components from word count or the reference example.
- Finish a set below 100%, then request fresh practice before its suggested review
  time. Generate analogous new items and a separate result; preserve the first set.
- Return after the suggested time and ask to review the errors. Use fresh retrieval
  tasks, without copying the old corrected sentences or treating prior help as
  independent evidence on those old tasks.
