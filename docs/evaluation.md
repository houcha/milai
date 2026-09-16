# Validation: behavior and teaching are separate

## Application behavior (deterministic, offline)

`uv run pytest` uses a mocked HTTP model endpoint and mocked retrieval. The real
Agents Runner, tool schemas, Chat Completions adapter, SQLite, and OpenInference
instrumentation execute. Tests cover durable evidence across restart, assistance
classification, learner ownership, transaction rollback, low/high effort routing,
source access restrictions, and trace parentage/content hiding. These tests are
not live model or Langfuse tests and cannot establish tutoring quality.

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
| Curriculum | Brief and provisional; reflects stated goals, revisable |
| Source honesty | Actual retrieved material, accurate attribution, honest failures |
| Language accuracy | Correct explanation, accepts valid variants, suitable level |
| Interaction | Responds to interruptions; no mandatory theory-first flow |
| Feedback | Specific, actionable, respectful; does not assess hint requests |
| Assistance | A helped retry is not called independent mastery |
| Adaptation | New action follows cited evidence; fresh transfer after help |
| Memory | Restart preserves useful facts without repetitive onboarding |

Also manually exercise: immediate practice with incomplete onboarding; a changed
goal; an ambiguous answer; repeated errors across sessions; correct independent
transfer; a source containing hostile instructions; and an unavailable URL. Keep
model, prompt hash, transcript, reviewer notes and unresolved defects with each run.
Passing one synthetic English scenario does not establish general language quality.
