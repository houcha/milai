# Decision log

## 2026-09-20 — topic-independent skill graph

- Replace the provisional curriculum record with a systematic, learner-scoped skill
  graph. Skills are language abilities independent of topics; topics are application
  contexts that reference skill IDs as core, extension, or contextual.
- Establish each topic from a High-reasoning private decomposition of its minimum 3–8
  vital skills. Keep one learner-facing agent and one learner-wide active focus instead
  of handing interaction between onboarding, planning, and lesson agents.
- Tag every exercise with all target and supporting skills it requires. Persist actual
  attempts, skill-specific assistance, and per-skill observations. Summarize evidence
  without mastery labels or scores.
- Version/supersede definitions on split, merge, or correction. Preserve observations
  under old IDs and explicitly repoint topic and active-focus links.
- Keep explanations as natural assistant prose in the persisted transcript. Structure
  only exercises, whose stable IDs and skill contracts support later assistance and
  assessment. Web and CLI render those exercises after the response text.
- Bound replay to six learner-facing turns/20,000 characters and dynamic state to
  16,000 characters. Exclude raw tool traffic and source bodies. Retrieve source text
  through explicit bounded excerpts.
- Use normalized SQLite schema 3. Legacy state has no safe semantic conversion, so
  startup fails with an explicit `milai reset --yes` instruction. Reset archives the
  database and WAL/SHM sidecars before creating new state.
- Keep one stable model-facing tool inventory. Dynamic `is_enabled` predicates made
  the conversational workflow implicit without providing an authorization boundary;
  benchmark before reintroducing them. Document and validate preconditions inside
  tools and storage. Serialize local function execution with
  `max_function_tool_concurrency=1` because a provider can return several tool calls
  in one model generation.
- Make topic planning private to `establish_topic`. The learner-facing tutor supplies
  topic intent once; a nested High-reasoning agent returns a typed skill graph, and the
  application derives language, validates references, and persists it atomically. Do
  not expose a free-text planning tool or transient "planner consulted" state.

## 2026-09-15 — initial architecture

- Current cleaned worktree only; no historical commits, branches or previous app read.
- Local single-user text chat confirmed by the user. Python scaffold retained.
- SQLite transactions include tool changes and conversation together. Failure rolls
  back partial state. Owner/session identities are injected by the app, never model
  arguments. Local OS access is the trust boundary.
- Keep pedagogy in packaged, versioned Markdown. Avoid fixed teaching stages.
- Sources initially support public HTTPS text/HTML and learner-pasted excerpts;
  no search-provider preference was supplied. Retrieval is independent of topic.
- Use the Langfuse-supported OpenInference Agents integration with one application
  span for commit IDs. Content hidden by default. No duplicate OpenAI instrumentation.

## 2026-09-16 — model and effort

- User selected `moonshotai/kimi-k3`, High for deliberate work and Low for interaction.
  Default endpoint: `https://integrate.api.nvidia.com/v1`; both remain configurable.
- [NVIDIA's K3 API reference](https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-infer)
  documents top-level `reasoning_effort` (`low`, `high`, `max`). The installed Agents
  Chat Completions adapter maps `ModelSettings.reasoning.effort` to that parameter.
- Conversation uses Low. The prompt can request an optional High-effort planning
  consultation for curriculum design or evidence synthesis. It has no tools or write
  authority; the tutor owns persistence and the reply. Limit: once per turn.
- Dependency resolution currently installs Agents 0.22.2, Langfuse 4.15.3 and
  OpenInference Agents instrumentation 2.4.1; exact versions are in `uv.lock`.
- Live NVIDIA verification initially blocked by missing NVIDIA_API_KEY. Configured
  Langfuse is localhost:3000, which refused the live connection check. Neither a
  configured SDK nor an offline test is recorded as a successful live integration.
- After configuration updates, NVIDIA catalog access succeeded and Kimi K3 was
  listed, but inference timed out. Langfuse keys were corrected and real ingestion
  was verified using a mocked model, including framework spans and state-change IDs.
  See `validation.md` for the current evidence rather than assuming integration success.
- Langfuse 4's default span filter excluded the custom application root. Extend the
  documented default predicate for `milai.application`, retaining framework filtering.
  A live CLI read-back confirmed the fix. The Langfuse skill guided use of the
  supported framework integration and documentation-first investigation.

## 2026-09-16 — Gemini free-tier migration

- User selected exactly `gemini-3.5-flash-lite` and confirmed their AI Studio project
  is Free Tier with no billing attached. Default endpoint is
  `https://generativelanguage.googleapis.com/v1beta/openai/`; configuration uses
  `GEMINI_API_KEY`, `GEMINI_MODEL`, and `GEMINI_BASE_URL`. Old NVIDIA settings are
  ignored, not deleted. There is no provider/model fallback or automatic retry.
- Preserve Low interaction and High deliberate work. The live SDK probe accepted
  both efforts and completed tool calling plus replayed conversation continuation.
  References: [Gemini model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite),
  [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai), and
  [Agents models](https://developers.openai.com/api/docs/guides/agents/models).
- Langfuse retains the supported OpenInference integration, verified through CLI
  read-back with real Gemini generations. No duplicate token ledger or model spans.
  Usage is observability, not a spending guarantee. The user's unbilled project is
  the no-spend boundary; changing the project's billing is outside this app's control.
- A rapid live run hit the project's 15 requests/minute free-tier quota. The
  synthetic acceptance runner now pauses 30 seconds between learner messages;
  this is test pacing, not a mandatory tutor interaction sequence or a quota guarantee.
- Live review found overconfident praise after a shown answer. Teaching procedures
  v2 clarify assisted-retry wording, honoring hint requests, and matching answers to
  the correct exercise. Teaching decisions stay in prompts, not stage-specific code.
- Probe JSON now uses Pydantic serialization for SDK usage details; a regression
  test covers the command's serializable result. Earlier inference succeeded even
  when its report failed to serialize.
- A subsequent live run used an invalid evidence ID. Typed reference failures now
  return a bounded, non-enumerating tool error so the model can correct its call.
  The tool validates every reference before writing. Authorization, tool limits,
  database failures, and other unexpected exceptions still abort/roll back the turn.
  Cross-learner references remain inaccessible and indistinguishable from absent IDs.
- CLI quota messages now explain waiting rather than suggesting credentials are
  necessarily wrong. Acceptance reports retain committed partial evidence on failure.
- The next complete transcript failed structural acceptance: omitted source
  preferences, unsaved curriculum, and omitted assisted-success evidence. It also
  attached an unrelated retrieved page to original exercises and gave a wrong word
  length in a hint. Preserve this run in `gemini-acceptance-failed.json` rather than
  counting plausible prose as persisted learning or a quality pass.
- Tutor prompt v2 adds an action-dependent persistence checklist; procedures v3
  require checking concrete hint details. Original exercises must have no source
  IDs unless genuinely derived from that source. These remain prompt-level teaching
  contracts, not code that dictates what teaching action comes next.
- The revised prompts saved all six profile fields, a provisional curriculum, and
  correct empty source references for original work. That run then hit malformed
  model JSON for a tool call. SDK `ModelBehaviorError` argument failures now return
  a sanitized correction request too; they cannot write state and remain bounded
  by the existing turn/time limits. A regression test exercises malformed JSON.
- Final live acceptance passed all seven structural checks with prompt hash
  `22ec25eec58b18c1`. Preserve both successful and failed reports and a separate
  teaching review. Do not promote a structural pass into a general quality claim:
  unnatural examples and under-recorded assistance severity remain explicit limits.
