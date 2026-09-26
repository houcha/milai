# Validation reports

## 2026-09-26 — Final exercise submissions

All 90 Python tests, browser/renderer Node tests, Ruff lint, and ty passed.
Regression tests cover repeat submission rejection, final
incorrect answers, missing-assessment rollback, and refresh-failure duplicate
prevention. Full scoring and visual validation follow in the next report.

## 2026-09-26 — Background answer checking

All 89 Python tests, browser/renderer Node tests, Ruff lint, and ty passed.
Regression tests cover duplicate submission prevention, independent pending
exercises, draft preservation, navigation away and back, and completion scoped
to the original lesson. HTTP tests hold the turn lock and an uncommitted write
while reading lesson/bootstrap data, verifying that reads finish promptly and
return only committed state.

Real Chromium checks with synthetic API data held an assessment open while
navigating and typing in another exercise. Completion preserved that field's
focus and value and the discussion draft. Reviewed screenshot:
[checking an answer in the background](screenshots/exercise-background-check.png).

## 2026-09-26 — Exercise responses stay on their cards

Offline checks passed all 88 Python tests, browser/renderer Node tests, Ruff
lint, and ty. Regression coverage verifies that pending, saved, and reloaded
answer turns stay out of discussion; assessment feedback is not duplicated;
unassessed clarification replies remain visible on the exercise; and submission
or refresh failures do not insert chat messages. Stored answers remain available
to the tutor.

Real Chromium checks with synthetic lesson/API data verified failed submissions,
corrections, completion, and reload without answer bubbles in discussion.
Explicit exercise questions still appear with their replies. Reviewed screenshot:
[exercise feedback beside discussion](screenshots/exercise-feedback-only.png).

## 2026-09-26 — Inline exercise blanks

Offline checks passed all 88 Python tests, browser/renderer Node tests, Ruff
format/lint, and ty. The Markdown bundle was regenerated with `npm run build:web`.
Coverage includes planner output and persistence of blank markers, count and
syntax validation, HTML escaping, unsupported-marker fallback, answer ordering,
required fields, draft isolation, failed submissions, retries, and completion.

Real Chromium checks with synthetic lesson/API data verified native required
fields, keyboard Tab order, drafts after reload, retained answers after failures
and incomplete assessments, completed answers as static text, and no horizontal
overflow at 390 × 844. Reviewed screenshots:
[desktop inline exercise](screenshots/inline-exercise-desktop.png) and
[mobile inline exercise](screenshots/inline-exercise-mobile.png).
No live model quality claim is made; the prompts and tool schemas now request
inline blanks when appropriate and separate numbered task lines.

## 2026-09-26 — Selected text in lesson discussion

Offline validation passed all 85 Python tests, the browser/renderer Node tests,
Ruff formatting/lint checks, and ty. Coverage includes full lesson context with
optional quotes, question/answer separation, persistence and replay, session
isolation, Unicode request bounds, schema-5 data preservation, and migration
rollback on failure. The synthetic acceptance runner now supplies quotes with
section and exercise questions; it was not run against a live model for this change.

Real headless Chromium checks with synthetic lesson/API data verified selections
across rendered formatting, sections, worked examples, and exercise feedback;
quote replacement/removal; failure retention and successful-send clearing;
saved quotes in history; and mobile tab switching and draft restoration on reload.
The 390 × 844 mobile viewport had no horizontal overflow. Reviewed screenshots:
[desktop selection](screenshots/lesson-selection-desktop.png) and
[mobile discussion](screenshots/lesson-selection-mobile.png).

The Markdown renderer was unchanged, so its bundle did not need rebuilding.

## 2026-09-25 — Lesson model default changed

Complete lesson and review generation now defaults to `gpt-6-sol` with low
reasoning and requested Fast processing. The compatibility probe and synthetic
teaching review below used the previous Luna configuration; they remain historical
results. Offline verification: `just qa` passed Ruff, ty, and all 75 Python tests. The
serialized generation request test confirms Sol, low reasoning, Fast tier, and
the unchanged 32,768-token budget.

A live `milai probe` passed tool use, replay, and Sol's low-reasoning structured
output request; the provider reported `fast` for that request. Probe trace:
`d05562acd1ad8c164b7b61fc1d256af8`. The subsequent full synthetic lesson
run did not finish during the diagnostic window and was interrupted during
`main_generation`; its [partial report](lesson-acceptance-sol-interrupted.json)
contains no committed lesson. Local Langfuse export was also unavailable. This
run establishes neither full-lesson compatibility nor teaching quality for Sol.

## 2026-09-25 — Complete lessons and scoped conversations

Validation is recorded in three separate layers so a passing contract does not
become a claim about teaching quality.

| Layer | Evidence from the previous Luna configuration |
| --- | --- |
| Model compatibility | The live `milai probe` completed a tool round trip and replay on `gpt-6-sol`, and a structured response on `gpt-6-luna` with `xhigh` and requested Fast mode. The provider reported `fast` as the processing tier for this request. Probe trace: `caf87d9c62e6db2636242b02d49390d5`. A Fast request does not guarantee that tier on every response. |
| Application contracts | The [live synthetic acceptance](lesson-acceptance.json) passed all 16 checks: complete lesson/card, scoped questions, answer assessment, continuation, discussion summary, focus, history isolation, and restart persistence. The [incomplete-answer run](lesson-acceptance-incomplete-answer.json) also passed all 16, with an `uncertain` assessment when required irregular forms were absent. Deterministic tests cover configuration, document/exercise validation, provider rejection and timeout rollback, scoped state, ownership, and browser navigation. |
| Teaching quality | [Assistant transcript review](teaching-review.md) is partial: feedback and pacing were useful, but the generated theory incorrectly labels the valid emphatic form “did go” as wrong. The planner prompt now requires accurate contrasts; this particular saved lesson remains an honest record of the observed output. This is not a learner study. |

The synthetic runner asked for a complete lesson, asked about a section and an
exercise, submitted a task-matched answer, continued from the lesson in main
chat, and reopened the session before another lesson question. The answer had
correct regular and irregular past verbs but omitted required `was/were`; the
tutor identified that omission, recorded a minor issue without mastery, left
prepared practice available, and deferred a new remedial drill. An initial
[exploratory run](lesson-acceptance-failed.json) did not assess an answer that
failed to address its selected fill-in task; the runner was corrected to choose
the independent writing task. The older Gemini reports below remain historical
evidence for the superseded design.

The browser layout was reviewed with this synthetic lesson at 1440 × 900 and a
true 390 × 844 emulated viewport. See the [desktop lesson](screenshots/lesson-desktop.png),
[desktop exercises](screenshots/lesson-desktop-exercises.png),
[narrow lesson](screenshots/lesson-narrow.png), and
[narrow discussion](screenshots/lesson-narrow-discussion.png) captures. The narrow
document width measured 390px, matching its viewport without horizontal overflow.

Final checks: `just qa` passed Ruff format/lint, ty, and 75 Python tests;
`npm run test:web` passed the browser/renderer Node tests; `uv build` produced
the wheel and source distribution. The checked-in Markdown bundle did not need
rebuilding because renderer source was unchanged.

## 2026-09-24 — Skill-focused lessons

- The full offline suite passed: 45 Python tests, browser tests, Ruff, and ty.
  The Responses mock supplies a platform value directly so its short-lived event
  loops close reliably on this Python 3.14 environment.
- No live model or teaching-quality result is claimed for this redesign.
- An offline distribution build could not resolve `setuptools>=69` from the local
  uv cache; packaging verification remains pending.

## 2026-09-16 — Historical report

> Historical report: this validates the curriculum/evidence prototype preserved in
> the linked artifacts. The 2026-09-24 lesson redesign replaces that schema and
> prompt. Its offline checks are maintained in the current test suite; a new live
> teaching-quality run has not yet been recorded.

## Completed

- **Offline application behavior:** 25 tests passed. The real Agents Runner, Chat
  Completions adapter, tool schemas, SQLite and OpenInference integration execute;
  model HTTP responses and source responses are mocked. This includes end-to-end
  learning-state persistence and a subsequent evidence-based action after restart.
- **Static checks:** Ruff formatting/lint and `ty check .` passed.
- **Packaging/CLI:** locked offline install and `milai --help` passed. Credentials
  missing from `.env` produce an actionable error without exposing their values.
- **Live public retrieval:** `https://example.com` returned available HTML, title
  `Example Domain`, a preserved URL/time and SHA-256 content hash. No model was
  involved in this check.
- **Live NVIDIA catalog:** `moonshotai/kimi-k3` appears in the configured endpoint's
  model listing; that request completed in 0.44 seconds.
- **Live Langfuse ingestion with a mocked model:** authentication and CLI read-back
  passed. [Verified synthetic trace](http://localhost:3000/project/cmu41ksw20003mf07z9v6ziwa/traces/a6ee95568f488f2342d479ec0f5c6fc8)
  has the name `language-tutor`, one application span, two generation spans (each
  20 input / 10 output tokens), one tool span, and committed learning-event IDs.
  Content remained hidden. These token counts are mock values; the Langfuse export,
  ingestion and read-back are real.

## Earlier integration failures

- The first NVIDIA request returned 401 because the supplied key omitted `nvapi-`.
  The user has since corrected the key. With the prefix restored, the compatibility
  probe timed out; a separate Low-effort 256-token request timed out after 45.4 seconds.
  A direct streaming request with a 120-second timeout also failed after 120.49 seconds
  without a first chunk. The latter two bypassed Agents orchestration, isolating the
  failure from the tutor's tools and persistence.
  Catalog availability is not evidence that inference or tool calling works.
- **Earlier tutoring checks:** a complete Gemini baseline failed structural and
  quality review; its actual transcript and state are preserved in
  `gemini-acceptance-failed.json`. Mock replies are never used as quality evidence.

## Gemini migration verification

- **Live Gemini compatibility: passed.** `gemini-3.5-flash-lite` at Google's
  OpenAI-compatible endpoint completed the unpredictable tool round trip, replayed
  conversation continuation, and Low/High effort requests. User confirmed Free Tier
  with no billing attached. No paid fallback or automatic retry is configured.
- **Live Langfuse with real Gemini: passed.** CLI read-back of
  [the probe trace](http://localhost:3000/project/cmu41ksw20003mf07z9v6ziwa/traces/006f6a608b0846a985e25621dc42711f)
  returned HTTP 200, four Gemini generation spans, one tool span, and the app root.
  Unlike the earlier trace, these are real model usage values, not mock fixtures.
- **Usage caveat:** the probe's first two requests report 244 input, 28 output, and
  291 total tokens in SDK usage. Langfuse normalizes those generations to 272 total
  (input + output). The integration does not preserve all provider usage detail;
  do not treat its total or estimated price as exact Gemini accounting or billing.
- The first unpaced learning run reached an assisted retry but hit the reported
  15 requests/minute free-tier quota before the restart action. A paced run then
  exposed an invalid evidence reference; no incorrect action was saved. The app
  now lets the model correct typed reference errors without relaxing authorization.
- A probe-report serialization error was fixed and regression-tested. It affected
  JSON output, not the already completed inference/tool calls.

## Completed live learning demonstration

- The final paced run passed **all seven structural checks**: profile persistence,
  provisional curriculum, actual retrieved source, exercise persistence, needs-work
  evidence, assisted success, and an evidence-referenced action after reopening SQLite.
- Model: `gemini-3.5-flash-lite`; prompt hash: `22ec25eec58b18c1`.
  [Full synthetic transcript and learning state](gemini-acceptance.json).
  The successful retry is saved with `independent_success=false`, and the
  post-restart teaching action references that success record.
- Langfuse CLI read-back returned all seven traces with 16 real generation spans:
  **94,330 input + 1,592 output = 95,922 normalized tokens**. This is the successful
  scenario only, not cumulative development usage. Replayed history and tool schemas
  count as input on every model request; seven learner messages are not seven calls.
  The usage-normalization caveat above still applies; these are not billing figures.
- All 15 committed learning-event IDs match the seven Langfuse application roots.
  [Post-restart trace](http://localhost:3000/project/cmu41ksw20003mf07z9v6ziwa/traces/9c1d68861dceec07e032369df7bf8549).
- **Teaching quality remains partial**, not a general quality certification. The
  [separate review](teaching-review.md) flags an unnatural example, overgeneralized
  grammar explanation, and under-recorded assistance severity. These do not become
  invisible just because the structural checks passed.

## Next verification

Prioritize exact assistance provenance (shown answer versus hint), natural original
examples, and fresh-task intent. Then expand live cases to changed goals, ambiguous
answers, repeated errors, unavailable sources, and independent transfer, across
languages. Retain the same separation between contract tests and teaching review.

## Live tracing issue found and fixed

Langfuse initially refused the connection, then rejected mismatched keys; the user
corrected both. The first successful export revealed that its current default filter
excluded the custom application span. Following the current Langfuse documentation,
the exporter now composes its default predicate with an exact allowlist entry for
`milai.application`. The second live read-back verified the root and learning-event
references; model and tool spans continue to come only from the supported integration.

An initial sandbox test run stalled asyncio thread wakeups. The suite passed outside
that sandbox. One approval attempt hit an account usage limit; a later approved run
completed successfully. Neither issue is represented as an application test pass.
