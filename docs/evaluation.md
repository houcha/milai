# Validation: behavior and teaching are separate

## Application behavior (deterministic, offline)

`uv run pytest` uses a mocked HTTP model endpoint and mocked retrieval. The real
Agents Runner, tool schemas, Chat Completions adapter, SQLite, and OpenInference
instrumentation execute. Tests cover schema reset, skill reuse, DAG validation,
supersession, stable tool inventory, runtime preconditions, required planning, structured activity
ordering, per-skill assistance/evidence, bounded prompts, learner ownership,
transaction rollback, source access restrictions, and trace privacy. These tests do
not use a live model or establish tutoring quality.

## Live integrations

`uv run milai probe` calls the configured Gemini model through the actual SDK. A
tool produces an unpredictable value, the model must return it, and a later turn
must recall it from replayed history without calling again. Run this before the
learning scenario. It emits endpoint/model, usage, result and trace ID. A configured
Langfuse client does not by itself prove server ingestion.

`uv run python -m milai.acceptance` runs a synthetic learner conversation using real
model and source requests, then closes/reopens SQLite before a subsequent action.
It prints the transcript, trace IDs and final state; `--report PATH` saves JSON.
By default it pauses 30 seconds between learner turns to ease free-tier rate limits
(not a quota guarantee); `--pause` overrides this. It never switches to paid capacity.
Its bounded acceptance messages
are a test fixture, not application orchestration. Failure to save any capability
fails the scenario; a human must still judge whether the teaching was good.

## Tutoring quality review

Score each item 0 (fails), 1 (partial), or 2 (clear success). Cite transcript turns.
No overall pass if source honesty or assistance distinction scores zero.

| Dimension | What a reviewer should look for |
| --- | --- |
| Discovery | Relevant follow-ups; unknown preferences remain unknown |
| Intent | Tutor elicits purpose instead of waiting for a curriculum request |
| Skill graph | Initial 3–8 skills are language-specific, minimal, reusable, and have real prerequisites |
| Focus | Current topic and target skills stay clear and move when intent changes |
| Source honesty | Actual retrieved material, accurate attribution, honest failures |
| Language accuracy | Correct explanation, accepts valid variants, suitable level |
| Interaction | Uses concise theory by default but responds to interruptions and requests to skip it |
| Feedback | Specific, actionable, respectful; does not assess hint requests |
| Assistance | A helped retry is not called independent mastery |
| Adaptation | Focus or graph changes follow evidence; fresh transfer follows help |
| Memory | Restart preserves useful facts without repetitive onboarding |

Also manually exercise: proactive intent discovery; the same skill reused in two
topics; a changed goal; an ambiguous answer; repeated errors across sessions; a
multi-skill task with help on only one skill; correct independent transfer; a source
containing hostile instructions; an unavailable URL; and a skill split/redefinition.
Keep model, prompt hash, transcript, reviewer notes and unresolved defects with each
run. Passing one synthetic English scenario does not establish general language quality.
