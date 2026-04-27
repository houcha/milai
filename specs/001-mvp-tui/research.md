# Research: AI-Native Language Learning (milai)

**Branch**: `001-mvp-tui` | **Date**: 2026-04-26

---

## Decision 1: LLM Model Selection

**Decision**: Default model profile is `light`, backed by `gemini/gemini-2.0-flash`. LLM parameters (model, temperature, top_p, max_tokens) are configured as named profiles under the `llm.profiles` section in `~/.milai/config.yaml`, with `llm.default_profile` selecting the fallback profile. State config may reference an LLM profile by name under `states.<state>.llm`, so user-facing conversational states can use a stronger model than structured content-generation states. API keys remain in environment variables exclusively (secrets must not be written to files).

**Rationale**:

The application's LLM requirements are specific and differ markedly from what most "latest" frontier models are optimised for:

| Requirement | Why it matters |
|---|---|
| Strong multilingual coverage | The core value proposition — must handle 30+ languages including non-European ones |
| Instruction following & structured JSON output | Every call returns a structured response; reliability matters more than reasoning depth |
| Low cost per token | Multiple LLM calls per session (assessment questions, lesson generation, exercise feedback, deviations); cost compounds |
| Fast time-to-first-token | TUI responsiveness depends on it |
| Does NOT need: complex reasoning, code generation, agentic tool use | These are the primary training objectives of most frontier "coding" models |

Models evaluated:

| Model | Multilingual | Cost (input/output per MTok) | Notes |
|---|---|---|---|
| `gemini/gemini-2.0-flash` | Excellent — Google's web-scale multilingual corpus | ~$0.10 / $0.40 | **Selected default**: Flash tier designed for efficiency, not deep reasoning; native structured JSON output; strong for 100+ languages |
| `openai/gpt-4o-mini` | Strong — 50+ languages well-covered | ~$0.15 / $0.60 | Good alternative; solid instruction following; weaker on rare languages |
| `anthropic/claude-haiku-4-5` | Good — English-dominant training | ~$0.80 / $4.00 | More expensive; Anthropic's multilingual data is narrower than Google's |
| `openai/gpt-4o` / `anthropic/claude-sonnet-4-6` | Excellent | $2–15 / MTok | Overkill; trained to excel at tasks we don't need; no cost justification |
| `mistral/mistral-small` | Good European languages, weak on Asian/rare | <$0.10 / MTok | Cheapest option; quality drops significantly for non-European languages |

**Why not the latest frontier model**: Frontier models (Opus, GPT-4o, Gemini Pro) are primarily trained and RLHF'd on coding, agent orchestration, and complex multi-step reasoning. These capabilities are irrelevant for generating pedagogically sound language exercises. The marginal quality gain does not justify a 5–15× cost increase per session.

**Why Gemini 2.0 Flash specifically**: Google's training corpus includes the multilingual web at a scale no other provider matches (Google Translate, Search, YouTube subtitles across 100+ languages). The Flash tier is explicitly designed for high-throughput, low-latency tasks — exactly our structured content-generation pattern. Structured JSON output is reliable. For rare target languages (e.g., Swahili, Welsh, Tagalog), Gemini's multilingual coverage is materially better than alternatives.

**Important qualification**: Free-form user-facing conversation has a different failure mode than theory/exercise generation. In deviation mode, the model must maintain tone, answer ambiguous learner questions, adapt explanations, and recover conversationally when the learner is confused. `gemini/gemini-2.0-flash` is a good default for structured assessment, curriculum, lesson, and feedback calls, but it may be too weak as the default for open-ended learner conversation. The architecture should therefore support routing conversational states to a stronger configured model without forcing all structured calls onto the expensive model.

**Configuration**:

LLM parameters are split by concern:

| Setting | Source | Reason |
|---|---|---|
| `llm.profiles.<profile>.*` | `~/.milai/config.yaml` | Non-secret named model profiles; user can tune a shared model choice in one place |
| `llm.default_profile` | `~/.milai/config.yaml` | Global fallback profile for states that do not choose one |
| `states.<state>.llm` | `~/.milai/config.yaml` | Optional per-state profile reference without coupling all state behavior to the LLM config section |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Environment variables | Secrets must never be written to files |

`~/.milai/config.yaml` default:
```yaml
llm:
  default_profile: light
  profiles:
    light:
      model: gemini/gemini-2.0-flash
      temperature: 0.7
      top_p: 0.95
      max_tokens: 1024
states: {}
```

Optional stronger model for user-facing conversation:

```yaml
llm:
  default_profile: light
  profiles:
    light:
      model: gemini/gemini-2.0-flash
      temperature: 0.7
      top_p: 0.95
      max_tokens: 1024
    heavy:
      model: openai/gpt-4o-mini
      temperature: 0.8
      top_p: 0.95
      max_tokens: 1536

states:
  deviation:
    llm: heavy
```

The initial v1 default config leaves `states` empty to keep setup simple. Recommended documented override: route `deviation` to a stronger conversational model profile when users notice shallow or brittle answers. State `llm` values must reference a key in `llm.profiles`; invalid profile names fail config validation at startup.

Config is loaded once at startup into a `Config` dataclass containing `llm: LLMProfilesConfig` and `states: dict[str, StateConfig]`. Missing file = use defaults. Missing keys = use per-key defaults. `StateConfig` initially contains only `llm: str | None`, but it is the intended place for future state-specific knobs such as deviation turn limits, retry behavior, or review thresholds.

The config loader validates profile references at startup. The entrypoint constructs one `LiteLLMClient` per configured profile, each with a single resolved `LLMConfig`. When constructing each state handler, the entrypoint chooses the handler's profile from `states.<state>.llm` or falls back to `llm.default_profile`, then passes the corresponding client into that handler's constructor. This keeps `LLMClient` unaware of app states, profile names, and routing tables while still allowing state-scoped model selection. The client does not read files or env vars directly (follows Principle V). Any LiteLLM-compatible model string is valid.

**Alternatives considered**: FSRS-style model-specific fine-tuning was considered but rejected (out of scope; LLM is the content engine, not a classifier).

---

## Decision 2: Workflow Architecture — State Machine

**Decision**: Hand-rolled state machine with `AppState` as a discriminated union of state variants, each carrying its own payload. One constructor-wired handler class per state. No external state machine library.

**Evaluation of alternatives**:

The user asked to evaluate this against alternatives. Here is the full analysis:

**Option A — Sequential async generator / coroutine chain**

The app flow could be expressed as a linear coroutine: `onboarding() → assessment() → curriculum_review() → learning_loop()`. Each function yields control to the next.

Problems:
- Resuming mid-flow requires reconstructing coroutine call stack from persisted state — not straightforward
- DEVIATION sub-state (free conversation during a lesson) requires suspending the lesson mid-exercise and re-entering it, which is awkward in a linear chain
- LLM failure retry (FR-013) at an arbitrary point in the chain requires exception propagation back to the right level
- Adding a new state (e.g., `ASSESSMENT_OVERRIDE`) requires modifying function signatures in the middle of the chain

**Option B — Event-driven message bus**

Each user action publishes an event; handlers subscribe. Decoupled but:
- Over-engineered for a linear flow with limited branching — YAGNI violation
- State is implicit (must be inferred from accumulated events)
- Resume from checkpoint requires event replay, which is complex

**Option C — State machine with discriminated union (selected)**

Each `AppState` variant maps to a handler class with a `step()` coroutine. The machine holds `AppState` and `UserState` as independent structures — `AppState` is workflow state (where we are + transient context); `UserState` is domain data (what the user knows). Transition = replace `AppState` with the new variant. Persistence = serialise both separately under two top-level keys in `state.json`.

Handler instances are composed at startup. Each handler receives only the dependencies it needs, typically `IOMediator`, the `LLMClient` selected for that state, and optionally that state's `StateConfig`. A handler does not load config, resolve model profiles, import LiteLLM, or save state.

Benefits:
- **Resume is trivial**: deserialise `AppState` + `UserState`, dispatch handler for the current variant
- **LLM retry is local**: each handler catches `LLMError`, shows retry prompt, loops — no re-entry complexity
- **DEVIATION carries its own payload**: `DeviationState` holds the context window directly — no separate nullable field, no risk of the buffer persisting outside DEVIATION
- **New states are additive**: add a union variant + handler class + dispatch branch + startup wiring
- **Testable in isolation**: instantiate a handler with fake `IOMediator` and fake `LLMClient`, then call `step(state, user)`
- **`UserState` stays clean**: no workflow fields contaminate the domain model
- **LLM routing stays simple**: profile selection happens once in `main.py`, not inside the LLM client or at every call site

**Verdict**: State machine is correct. The user's intuition is validated by the resume and deviation requirements, both of which are genuinely difficult in alternatives.

**Dispatch mechanism**: `match/case` in `machine.py`. Each `case StateVariant():` branch calls the corresponding handler instance, e.g. `handlers.deviation.step(app, user)`, and narrows the type for `ty` — no casts needed. The full graph topology is visible in one readable dispatch function.

**Handler class guardrails**:

- `AppState` and `UserState` models remain pure Pydantic data; they do not contain behavior.
- Handler classes coordinate one workflow step; they do not perform persistence or own serialization.
- `StorageClient` is used only by the machine loop, after a handler returns the next `(AppState, UserState)`.
- Prompt construction stays in `src/milai/llm/prompts/`; handlers call prompt builders rather than embedding large prompt strings.
- Concrete provider details stay in `LiteLLMClient`; handlers depend only on `LLMClient`.

**Why no library or decorator pattern** (`transitions`, `statemachine`, hand-rolled `@machine.node()`): Our state graph has 9 states. A library or decorator abstraction imposes indirection for no gain at this scale. `match/case` already gives you the explicit node list in one readable place. YAGNI applies — the hand-rolled version is ~20 lines and requires zero infrastructure.

**State variants**:

```
OnboardingState           → collect language + preferences
AssessmentState           → LLM-generated adaptive test (resumable); holds questions + cursor
AssessmentReviewState     → show fluency result; allow user override; holds pending fluency level
CurriculumGenerationState → LLM generates structured roadmap
CurriculumReviewState     → human-in-the-loop edit loop
LessonState               → sequential theory + exercises
DeviationState            → free conversation; holds context window + lesson context
LessonCompleteState       → show progress, advance cursor
CurriculumCompleteState   → show summary, offer extension
```

---

## Decision 3: Local Storage Format

**Decision**: Single JSON file at `~/.milai/state.json`; atomic writes via `tempfile` + `os.replace`.

**Rationale**:

The persisted object is the entire `UserState` — a single root structure. Read/write patterns:
- **Read**: once at startup
- **Write**: after every state transition and after each exercise completion

Data volume: a full curriculum + all skills fit comfortably within a few KB. No query patterns require an indexed database.

SQLite was evaluated: it adds a dependency and ORM/schema migration complexity for a dataset that is trivially small and requires no partial queries. Overkill.

JSON with atomic writes (write to `~/.milai/state.json.tmp`, then `os.replace`) is crash-safe, human-readable (users can inspect/backup their data), and zero-dependency.

---

## Decision 4: Spaced Repetition Algorithm

**Decision**: Custom lightweight scheduler inspired by SM-2. Integrated into LLM prompt construction; not a separate review session.

**Rationale**:

Full SM-2 / FSRS is designed for flashcard-style review sessions with discrete recall events. Our model is different: skills are topic-level (e.g., "past tense"), not individual cards, and SRS signals feed the LLM prompt rather than driving a standalone review queue.

**Chosen algorithm** (per-Skill):

```
On successful exercise for topic T:
    strength = min(1.0, strength + 0.1)
    streak += 1
    interval_days *= 2.0  (capped at 90)

On failed exercise for topic T:
    strength = max(0.0, strength - 0.2)
    streak = 0
    interval_days = 1.0

due_for_review(skill) = (today - last_seen).days >= interval_days
```

**Integration with lesson generation**: When the LLM generates exercises for a lesson, the prompt includes the top-3 skills ranked by `priority = (1 - strength) * log(days_overdue + 1)`, with explicit instructions to weave them into the exercise set alongside the new lesson topic. This blends weak-spot reinforcement into regular lessons without a separate review session.

---

## Decision 5: Context Window Management

**Decision**: Stateless per-call context. Conversational context window only in DEVIATION mode (capped at 10 exchanges).

**Per-call context budget (structured prompt)**:
1. System role prompt (~200 tokens): tutor persona + target language + teaching style
2. User skill summary (~150 tokens): top-10 skills by priority (topic, strength, last_seen only)
3. State-specific context (~300–800 tokens): current lesson/exercise or assessment answers
4. User message (~50–200 tokens)

Total typical prompt: ~700–1200 tokens. Response: ~300–600 tokens. Per-call cost on Gemini 2.0 Flash: ~$0.0001–$0.0002. Reasonable.

**Deviation mode**: Maintains rolling window of last 10 exchanges (user + assistant). Older exchanges are dropped. On deviation exit, the context window is discarded — the lesson context is reconstructed from `UserState`.

**No cross-state context accumulation**: Each state handler builds its context fresh from `UserState`. This keeps prompts predictable, bounded, and testable.

---

## Decision 6: Sub-agents

**Decision**: No sub-agents in v1.

**Rationale**: Every LLM call in v1 is a single-turn, single-purpose request:
- Assessment question N → one call
- Curriculum generation → one call (full structured JSON)
- Lesson content → one call
- Exercise feedback → one call
- Deviation turn → one call

None of these require coordination between concurrent agents. Curriculum generation returns the full roadmap in one structured response — this is preferred over parallel module generation because it ensures narrative coherence across modules (a sub-agent approach would require a synthesis step that adds complexity and a failure mode).

Sub-agents become relevant in v2 if: (a) full curriculum generation exceeds model context limits for long curricula, or (b) parallel module refinement is needed for quality. Both are deferred.

---

## Decision 7: LiteLLM + Instructor for Structured Output

**Decision**: Use `litellm` directly with JSON mode + Pydantic validation. Add `instructor` only if provider coverage requires it.

**Rationale**: LiteLLM's `completion()` with `response_format={"type": "json_object"}` works across all major providers. Pydantic `model_validate_json()` parses and validates the response. If a provider doesn't support JSON mode reliably, `instructor` (which wraps LiteLLM and adds retry-on-parse-failure) can be dropped in at the `LLMClient` implementation layer without changing any call sites, because all call sites go through the `LLMClient` protocol.

Start with plain LiteLLM + Pydantic validation. Add `instructor` as a concrete implementation detail if parse reliability is a problem in practice.
