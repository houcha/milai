# Decision log

## 2026-09-27 — Recover from duplicate active-skill selection

- Keep one active lesson per current focus: requested extra practice appends to
  its existing document rather than creating a duplicate lesson.
- Return actionable `invalid_operation` guidance when a valid generated draft
  selects that active skill. Check before saving; keep the one-generation-per-turn
  bound and rollback behavior for unexpected validation and operational failures.

## 2026-09-27 — Mastery describes evidence, not permission to advance

- Remove direct and transitive prerequisite mastery gates from lesson creation.
  Keep ownership, language, reference, and acyclic graph validation.
- Explicit continuation chooses another appropriate skill even after incorrect
  or incomplete practice. Explain necessary background inside that lesson.
  Reviews remain optional; mastery, scores, and review timing are unchanged.
- This supersedes earlier decisions requiring mastery before progression.

## 2026-09-26 — Final answers and practice-set accuracy

- Replace correction loops with one saved submission per exercise, regardless of
  correctness. Keep feedback on the card. Failed model transactions remain retryable.
- Show an accuracy rate only after every exercise in a generated set is submitted.
  Default to partial credit for explicitly requested components in new assessments;
  distinguish that rate from mastery. Preserve a labelled whole-exercise rate for
  legacy sets without component counts, rather than inventing partial scores.
- Group later fresh practice by its generating turn and preserve each set's result.
  Show the latest result beside its lesson so learners can identify practice to
  revisit; do not overwrite original answers or inflate them with corrections.
- Default review timing to an advisory 24 hours after completing a set. A hard
  cooldown is not enabled; the learner can read, discuss, and request practice sooner.
- Upgrade schema 5/6 transactionally to schema 7 with nullable attempt score data.
  Previous correction-loop decisions below are superseded.

## 2026-09-26 — Check exercise answers in the background

- Scope pending answer state and disabled controls to the submitted exercise.
  Keep navigation, reading, other exercises, and discussion drafting available.
  Preserve other fields and focus by updating only the assessed card.
- Keep model writes serialized, but serve lesson and bootstrap reads from
  separate read-only snapshots so navigation sees committed data immediately.
- Capture the originating session, lesson, and exercise for asynchronous work;
  navigation must not redirect feedback or clear another lesson's draft.

## 2026-09-26 — Exercise responses stay on their cards

- Do not replay answer submissions or assessment replies in the browser's
  discussion chat, including temporary bubbles, saved history, and fallback
  paths after errors. Keep questions about exercises in discussion.
- Show answer progress, recorded feedback, and unassessed clarification replies
  on the owning exercise. Retain persisted turns and model history so discussion
  can still use the learner's exercise evidence. Preserve discussion scroll
  position while an answer is processed.

## 2026-09-26 — Inline short-answer exercises

- Let the model choose inline blanks for words or short phrases and ordinary
  free text for open-ended writing. Use Markdown ordered lists with one item
  per line for multi-part tasks. The general teaching contract applies to new
  lessons and appended practice; existing saved tasks keep their original format.
- Extend task Markdown with `{{blank}}`, up to 12 occurrences in reading order.
  The app owns the actual inputs; model HTML and scripts remain disabled.
  Preserve the existing task schema and database. Terminal output uses numbered
  static blanks. Unsupported marker placement falls back to free-text entry.
- Submit all blanks together to the existing tutor assessment. Each field takes
  up to 200 characters; drafts survive reload and failure. Preserve submitted
  answers for correction, and replace completed inputs with plain answer text.
  Blank widgets alone do not change assistance or mastery rules.

## 2026-09-26 — Selected text focuses lesson questions

- Always provide the complete lesson to lesson discussion. Replace section and
  exercise question buttons with optional highlighted text, automatically attached
  as a removable quote without switching tabs or moving focus. Derive a section,
  worked-example, or exercise reference from its DOM location when unambiguous.
- Keep one quote for the next discussion question, preserve it with the draft on
  reload and failure, and clear it after successful commit. Store it with the turn
  for display, bounded replay, and retrieval. Quotes are learner-provided context,
  not instructions or verified sources. Highlighting alone records no evidence.
- Answer submissions retain their explicit exercise ID and never carry a quote.
  Typing or submitting an answer no longer sets later discussion focus. Completed
  exercises show prior answers and feedback without answer controls.
- Schema 6 adds nullable turn quote text. Upgrade schema 5 transactionally while
  preserving existing data; older incompatible schemas still require archival reset.
  Retain historical section/exercise references and existing API callers.

## 2026-09-25 — Sol lesson generation at low reasoning

- Generate complete lessons and reviews with `gpt-6-sol` at low reasoning by
  default. Keep generation's separate model configuration, requested Fast tier,
  32,768-token combined reasoning/output budget, and 32,000-character document
  cap. Chat remains on its independently configured model and processing setting.
- The earlier Luna probe and teaching review remain historical evidence; they do
  not establish the quality of Sol-generated lessons.

## 2026-09-25 — Complete lessons with dedicated conversations

- Keep main chat for direction and explicit continuation. A generation turn saves
  one fixed lesson document, its initial three to six exercises, an Open lesson
  card, and the main reply atomically. Generated lessons form a history, not a
  prospective roadmap. The learner can revisit any lesson without changing the
  session's current teaching focus.
- Give each lesson one persistent conversation. Turns carry lesson and optional
  section or exercise references. Questions and answer submissions are distinct;
  section or exercise discussion does not itself create an attempt. A bounded
  rolling summary retains unresolved questions and next steps. Main and lesson
  histories replay separately while sharing explicit profile facts and evidence.
- Use the configured `OPENAI_MODEL` at low reasoning for main chat, discussion,
  assessment, and additional practice. Generate full lessons and reviews with
  `gpt-6-luna`, `xhigh` reasoning, Fast tier, and a 32,768-token output budget by
  default. The document text has a separate 32,000-character cap. Both model
  instances share one authenticated client; unsupported configurations, errors,
  and timeouts abort the turn without fallback or retry.
- Preserve prerequisite and independent-mastery rules. After a minor slip,
  prepared exercises remain available while new remedial drills follow the
  delayed-review rule unless requested. Assessments recommend due reviews;
  explicit continuation lets main chat select the next eligible lesson or review.
- Use schema 5 for lesson documents, scoped turns, summaries, focus, and direct
  presentation links. Existing databases require `milai reset --yes`, which
  archives the old database. Browser navigation opens stored lessons directly,
  with a reading area and adjacent discussion; the terminal uses `/lessons`,
  `/lesson`, `/back`, and `/answer`.
- The 2026-09-25 small-error entry and older decisions below record the previous
  implementation where they disagree with this entry.

## 2026-09-25 — Defer small-error review

- Record whether an observed target error is minor or substantial. A mostly correct
  answer with a minor slip can be an independent success; substantial difficulty
  retains the existing mastery reset. Unclear evidence remains uncertain.
- Close a mostly correct exercise, correct the slip briefly, and block another
  exercise on that skill until two distinct exercises on other skills have been
  attempted. An explicit learner request can bring it back earlier. The later check
  opens a Review lesson after the current skill is mastered, using the existing
  lesson history.
- Add `issue_severity` to existing schema 4 databases in place. Historical outcomes
  remain unchanged and have no inferred severity.

## 2026-09-24 — Skill-focused lessons replace topics

- Replace topics, topic links, and focus history with chronological lessons. A lesson
  has one language skill as its focus and remains active across turns. The path title
  is derived from language and skill; revisits create a separate Review entry.
- Plan only the next skill, with no 3–8 skill inventory. Prerequisite edges remain
  a DAG. Every ancestor prerequisite must be mastered before teaching a dependent
  new skill, even after an explicit advanced request. The tutor explains the detour.
- Mastery is two independent successes on distinct exercises since the latest
  `needs_work` observation. Scaffolded, assisted, and uncertain outcomes do not
  qualify. Practice has one current-lesson target and may use prior lesson skills
  as support. Repeated difficulty or a learner request can trigger a review lesson.
- Store schema 4 requires an explicit archival reset from schema 3. No migration is
  attempted. The browser path and skill view now show lessons and derived mastery.
- Earlier decisions below describe the prior topic model and are retained as history.

## 2026-09-24 — Tutor-selected teaching examples

- The tutor supplies examples that fit the learner's goal and level. Once language,
  purpose, and starting point are known, it should teach instead of requesting
  optional details as a prerequisite.
- When authentic material is relevant, the tutor may analyze a confidently
  recalled title or very short phrase with natural attribution. Recalled wording
  is not a verified source and has no saved source ID. Close reading still uses a
  learner-pasted passage or learner-supplied URL; retrieval does not expand into
  web search.

## 2026-09-24 — GPT-6 Luna Responses migration

- Replace the Gemini Chat Completions provider with OpenAI's Responses API and
  `gpt-6-luna`. Keep Low reasoning for tutoring and High for private topic planning;
  Chat Completions cannot combine Luna tool calls with those reasoning settings.
- Use `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL`; the existing Gemini
  variables are ignored. Keep the existing local SQLite history and no-retry policy.
- Send `store=false` and include encrypted reasoning content for in-run tool
  continuation. The Agents SDK supplies response usage to OpenInference, which
  masks input/output before Langfuse export unless content tracing is enabled.
- The uncommitted 300-second request and turn timeouts are retained. Live requests
  require a paid OpenAI project; offline mocks do not establish model quality.

## 2026-09-24 — submit before continuing

- Remove Review explanation and Back to conversation from the practice view. Neither
  added an explanation; both recorded blanket assistance on exit. Continue appears
  after the first submitted answer receives a reply, whether or not it was correct,
  and returns to conversation without a review event. The learner may retry or
  continue after a clarification.

## 2026-09-23 — remove exercise hints

- Exercises no longer generate or reveal private hints. Answer turns carry only the
  selected exercise ID to the tutor.
- Explanations and shown answers still record assistance, so helped retries do not
  count as independent success. Existing hint records remain readable in older
  databases, but new databases and tool calls cannot create them.

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
