# Validation report — 2026-09-16

> Historical report: this validates the curriculum/evidence prototype preserved in
> the linked artifacts. The 2026-09-20 topic-independent skill-graph redesign replaces
> that schema and prompt. Its offline checks are maintained in the current test suite;
> a new live teaching-quality run has not yet been recorded.

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
