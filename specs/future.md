# Future Work & Deferred Decisions

**Date**: 2026-04-24

Items here are intentionally out of scope for v1. They are recorded to prevent re-litigation and to give v2/v3 a clear starting point.

---

## LLM Telemetry (v3)

User-facing interaction review and developer-facing LLM observability are both deferred beyond v1. Developer-facing observability includes prompt traces, latency, token cost per call, and eval scores.

**Recommended tool**: Langfuse (open-source, self-hostable via Docker). It provides trace capture, dataset management for fine-tuning, and eval pipelines — directly useful for the preference-tuning use case.

**Integration pattern**: Wrap `LiteLLMClient` with a `LangfuseTracingClient` decorator that forwards every call to both the underlying client and the Langfuse SDK. No state machine or prompt code changes required — the `LLMClient` Protocol absorbs the change entirely.

---

## Multi-user and Multi-session Support (v4)

Multi-session support is intentionally deferred until database-backed multi-user persistence. In v1/v2, the product keeps one persisted learning session per installation; adding multiple local sessions now would require session selection, naming, deletion, and migration mechanics before the durable user identity model exists.

When multi-user support is introduced, model sessions as learning contexts owned by a user: one user can have many sessions, and each session owns its target language, curriculum, progress, assessment state, and interaction log. This is when independent tracking for multiple target languages should be added, rather than making v1 carry parallel language tracks inside one local state file. This should come with auth, user profiles, session listing/resume UX, and a migration path from local single-session storage to a networked database (e.g., PostgreSQL). The `StorageClient` Protocol absorbs the backing-store change; add a separate interaction-log interface only once that future version needs it.

---

## Sub-agent Parallelism (v5+)

Parallel module generation for large curricula if single-call quality proves insufficient. Deferred because: all v1 LLM calls are single-turn; curriculum is generated coherently in one structured call; sub-agent coordination adds complexity with no demonstrated need.
