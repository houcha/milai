# Future Work & Deferred Decisions

**Date**: 2026-04-24

Items here are intentionally out of scope for v1. They are recorded to prevent re-litigation.

---

## Curated Skill Registry

Customization is a differentiating feature, but curriculum generation should not depend on the model inventing the educational map from memory at runtime. Introduce a **versioned skill registry** with relationship metadata: stable skill definitions, prerequisites, difficulty levels, tags, related skills, and contrasts.

Personalized roadmaps should still be generated per learner from the skill registry plus learner state, goals, native language, interests, observed errors, time constraints, and preferred learning style. The planner/LLM can choose a path through the registry, adapt pacing, and generate examples, but lessons and exercises should reference known skill IDs and satisfy registry constraints. Exercises should be allowed to combine the new target skill with already learned skills so learners practice interactions between concepts instead of pattern-matching isolated drills.

The agent should infer the learner's actual mistakes from interaction history and generate examples, explanations, and checks from the current learner context, grounded by the skill registry.

Start with curated offline registries for popular languages because core language structure is relatively static. Use separate dynamic overlays for fast-changing or regional material such as slang, modern idioms, dialect variation, and user-specific custom skills. LLM-proposed additions should enter as temporary or untrusted records until sourced, validated, or reviewed.

---

## Curated Source Corpus

Milai should not rely only on the model's internal memory for language facts, usage guidance, or pedagogical claims. Introduce a **curated source corpus**: a reviewed collection of high-quality grammar references, usage references, CEFR-like descriptors, pronunciation references, and other trusted materials that the agent can consult for grounding, ambiguity resolution, and citations.

The corpus is reference material, not prewritten lesson content. It should not require curating static examples, common mistakes, fixed assessments, or generic roadmaps. Runtime generation should still create examples, exercises, explanations, and checks from the learner's current context. The corpus exists to make those generated materials better grounded and easier to audit.

The corpus should be ingested into citable sections with metadata such as language, topic, dialect or register, proficiency level, source type, provenance, and review status. Prefer deterministic metadata lookup for known needs, such as "Spanish A2 preterite explanation" or "formal French register guidance." Use semantic retrieval/RAG only when metadata lookup is insufficient, such as ambiguous usage questions, disputed explanations, or current language variants.

---

## LLM Telemetry

User-facing interaction review and developer-facing LLM observability are both deferred beyond v1. Developer-facing observability includes prompt traces, latency, token cost per call, and eval scores.

**Recommended tool**: Langfuse (open-source, self-hostable via Docker). It provides trace capture, dataset management for fine-tuning, and eval pipelines — directly useful for the preference-tuning use case.

**Integration pattern**: Wrap `LiteLLMClient` with a `LangfuseTracingClient` decorator that forwards every call to both the underlying client and the Langfuse SDK. No state machine or prompt code changes required — the `LLMClient` Protocol absorbs the change entirely.

---

## State-specific UI Snapshots

The v1 TUI uses a single generic interaction layout: a transcript surface plus one prompt/input or button row. This matches the narrow `IOMediator` contract (`show`, `prompt`, `choose`, `confirm`, `clear`) and is useful scaffolding, but it should not be treated as the long-term product UI model.

A product UI may be easier to reason about as **state-specific UI snapshots**: assessment, curriculum review, lesson, feedback, deviation handling, and completion can each have their own view structure and local UI logic. This keeps "where the learner is" visually explicit and puts state-specific presentation decisions in one place instead of encoding the whole product as a chat-like stream of generic interactions.

The transition should preserve the core boundary: workflow state and domain logic must remain independent of terminal UI, FastAPI, or browser APIs. A future implementation can introduce a renderer/controller registry parallel to the existing handler registry:

```text
AppState variant -> StateHandler
AppState variant -> StateRenderer or StateController
```

There are two viable levels of change:

1. **State-aware mediator, handlers unchanged**: the state machine tells the mediator the current `AppState`, and handlers still call generic mediator methods. This is a smaller migration, but UI sequencing remains partly embedded in handlers.
2. **State-specific controller/action model**: each state owns a view model, accepted user action type, and transition logic. This is a larger migration, but it gives each state one obvious home for its UI snapshot and action contract.

### Optional LangGraph Compatibility

If migrating toward LangGraph, prefer keeping a state's view model, accepted action, and transition logic adjacent unless there is a concrete reason to split UI and handler into separate graph nodes. Separate UI and handler nodes can drift because they share an implicit action contract. A single state-specific node/controller can build a deterministic serializable view model, receive a typed action, then perform LLM/domain work and return the next state.

LangGraph compatibility favors serializable view/action payloads over live UI calls. If using human-in-the-loop interrupts later, keep pre-interrupt work deterministic and side-effect-light, then validate the resumed action and perform LLM/storage side effects after the interrupt resumes.

---

## Multi-user and Multi-session Support

Multi-session support is intentionally deferred until database-backed multi-user persistence. In v1/v2, the product keeps one persisted learning session per installation; adding multiple local sessions now would require session selection, naming, deletion, and migration mechanics before the durable user identity model exists.

When multi-user support is introduced, model sessions as learning contexts owned by a user: one user can have many sessions, and each session owns its target language, curriculum, progress, assessment state, and interaction log. This is when independent tracking for multiple target languages should be added, rather than making v1 carry parallel language tracks inside one local state file. This should come with auth, user profiles, session listing/resume UX, and a migration path from local single-session storage to a networked database (e.g., PostgreSQL). The `StorageClient` Protocol absorbs the backing-store change; add a separate interaction-log interface only once that future version needs it.

---

## Sub-agent Parallelism

Parallel module generation for large curricula if single-call quality proves insufficient. Deferred because: all v1 LLM calls are single-turn; curriculum is generated coherently in one structured call; sub-agent coordination adds complexity with no demonstrated need.
