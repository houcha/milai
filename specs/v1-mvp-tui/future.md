# Future Work & Deferred Decisions

**Branch**: `v1-mvp-tui` | **Date**: 2026-04-24

Items here are intentionally out of scope for v1. They are recorded to prevent re-litigation and to give v2/v3 a clear starting point.

---

## LLM Telemetry (v2/v3)

The history DB (`~/.milai/history.db`) covers *user-facing* history — conversations and exercises a learner can review. A separate concern — *developer-facing LLM observability* (prompt traces, latency, token cost per call, eval scores) — is deferred until the system moves server-side in v2.

**Recommended tool**: Langfuse (open-source, self-hostable via Docker). It provides trace capture, dataset management for fine-tuning, and eval pipelines — directly useful for the preference-tuning use case.

**Integration pattern**: Wrap `LiteLLMClient` with a `LangfuseTracingClient` decorator that forwards every call to both the underlying client and the Langfuse SDK. No state machine or prompt code changes required — the `LLMClient` Protocol absorbs the change entirely.

---

## Web Interface (v2)

Implement `ApiMediator` (FastAPI + WebSocket/SSE) alongside the existing `TextualMediator`. The `IOMediator` Protocol absorbs the change — no state machine code requires modification. Docker packaging added at this point.

---

## Multi-user Support (v2)

Requires auth, per-user namespacing of `state.json` and `history.db`, and a migration path to a networked database (e.g., PostgreSQL). The `StorageClient` and `HistoryClient` Protocols absorb the backing-store change.

---

## Sub-agent Parallelism (v2+)

Parallel module generation for large curricula if single-call quality proves insufficient. Deferred because: all v1 LLM calls are single-turn; curriculum is generated coherently in one structured call; sub-agent coordination adds complexity with no demonstrated need.
