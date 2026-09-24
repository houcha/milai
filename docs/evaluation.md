# Validation: behavior and teaching are separate

## Application behavior (deterministic, offline)

`uv run pytest` uses a mocked HTTP model endpoint and mocked retrieval. The real
Agents Runner, tool schemas, Responses adapter, SQLite, and OpenInference
instrumentation execute. Tests cover schema reset, one-skill lessons, prerequisite mastery, independent evidence,
review entries, session isolation, exercise contracts, and lesson navigation. Other tests
cover source restrictions and trace privacy. These tests do
not use a live model or establish tutoring quality.

## Live integrations

`uv run milai probe` calls the configured GPT-6 Luna model through the actual SDK. A
tool produces an unpredictable value, the model must return it, and a later turn
must recall it from replayed history without calling again. Run this before the
learning scenario. It emits endpoint/model, usage, result and trace ID. A configured
Langfuse client does not by itself prove server ingestion.

`uv run python -m milai.acceptance` runs a synthetic learner conversation using real
model and source requests, then closes/reopens SQLite before a subsequent action.
It prints the transcript, trace IDs and final state; `--report PATH` saves JSON.
By default it does not pause between learner turns; `--pause` adds a delay if needed.
The run uses paid API capacity and no provider fallback.
Its bounded acceptance messages
are a test fixture, not application orchestration. Failure to save any capability
fails the scenario; a human must still judge whether the teaching was good.

## Tutoring quality review

Score each item 0 (fails), 1 (partial), or 2 (clear success). Cite transcript turns.
No overall pass if source honesty or assistance distinction scores zero.

| Dimension | What a reviewer should look for |
| --- | --- |
| Discovery | Asks about unknown experience before teaching; accepts uncertainty and shortcuts; avoids repeated onboarding |
| Intent | Tutor elicits purpose instead of waiting for a curriculum request |
| Lesson skill | One precise language ability is the new focus; the lesson title names that skill |
| Focus | One skill stays current across turns; examples do not change it |
| Source honesty | Actual retrieved material, accurate attribution, honest failures |
| Language accuracy | Correct explanation, accepts valid variants, suitable level |
| Interaction | One coherent objective with enough related forms and worked examples; incidental features of examples do not derail the lesson; practice begins when useful |
| Feedback | Specific, actionable, respectful; does not assess questions as attempts |
| Assistance | A helped retry is not called independent mastery |
| Adaptation | Review follows repeated difficulty; prerequisites are mastered before progression |
| Memory | Restart preserves useful facts without repetitive onboarding |

Also manually exercise: proactive intent discovery; the same skill reused in a review
lesson; a changed goal; an ambiguous answer; repeated errors; an advanced request
with unmet prerequisites; help on one skill; independent transfer; a hostile source;
an unavailable URL; and a skill redefinition.
Keep model, prompt hash, transcript, reviewer notes and unresolved defects with each
run. Passing one synthetic English scenario does not establish general language quality.

## Calibration and coherence review

Review these synthetic conversations with the current model and prompt hash. Record
transcripts and reviewer findings; mocked planner tests verify context delivery only.
Live pedagogical validation of this change remains pending until these runs are reviewed.

| Scenario | Expected behavior |
| --- | --- |
| A language and learning goal, with no prior evidence | Ask about experience and wait before selecting lesson content |
| Same goal, "starting from scratch" | Save the reported level; teach one accessible objective with meaning, a pattern, and a worked example |
| Same goal, "comfortable reading German novels" | Use an appropriate challenge without automatically reteaching elementary grammar |
| "I'm not sure of my level" | Offer a small diagnostic instead of repeating the level question |
| Returning learner with relevant saved evidence | Use that evidence and avoid repeated onboarding; distinguish assisted from independent success |
| "Skip the questions; give me something to try" | Allow immediate manageable practice and adapt from the response |
| "Explain more slowly" or "I know this; move faster" | Adjust depth and pace while retaining a clear objective |
| Beginner asks for all German subject pronouns before practice | Explain ich, du, er, sie, es, wir, ihr, sie, Sie with meanings and contrasting examples; do not present an exercise after only three forms |
| Learner wants to learn German through Rammstein, is starting from scratch, and has no song in mind | Choose a short, accessible title or confidently known phrase to anchor one useful objective; develop that objective before moving to other grammar or pronunciation, and do not ask them to pick a song before teaching |
| After a brief title illustrating a pronoun, the learner needs the pronoun system | Explain the useful pronoun set, meanings, and key contrasts before exploring the title's verb form, pronunciation, or another title |
| Learner supplies a short passage from "Deutschland" and asks for analysis | Identify the pronouns actually present, explain their referents and verb forms, and distinguish other forms supplied in original examples; do not force an exercise |
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
| Beginner asks for an advanced construction with unmastered prerequisites | Tutor chooses the earliest teachable prerequisite, explains the relationship, and does not teach the advanced construction yet |
| One error on the current skill | Tutor explains and continues the same lesson |
| Repeated difficulty on a previously taught skill | A separate Review lesson appears; earlier path entry remains |
| Two independent successes on distinct unscaffolded exercises | Skill becomes mastered unless a later `needs_work` observation resets the count |
| An assisted or scaffolded success | Evidence is saved but does not advance mastery |
| A later lesson uses an earlier skill | Exercise targets the current new skill and tags the earlier skill as supporting |
