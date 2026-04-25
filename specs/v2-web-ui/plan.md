# Implementation Plan: v2 Web UI

**Branch**: `v2-web-ui` | **Date**: 2026-04-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/v2-web-ui/spec.md`

## Summary

Add a browser UI without changing the learning engine. The selected implementation is a single Python web process built on FastAPI + Uvicorn, serving a small static frontend (HTML/CSS/JS with Alpine.js and Marked.js) and a WebSocket endpoint that backs `ApiMediator`. The existing state machine, handlers, SRS, provider interfaces, and TUI mode remain intact; v2 adds a second `IOMediator` implementation plus Docker packaging.

The key architectural choice is to use FastAPI directly rather than Streamlit or Gradio. This feature needs explicit control over WebSocket lifecycle, persistent session cookies, reconnect behavior, and a thin translation layer from `IOMediator` calls to browser messages. FastAPI fits that shape directly. Streamlit and Gradio are productive when the framework owns the app flow, but here the app flow is already owned by milai's state machine.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: `fastapi` (ASGI app + WebSockets + static files), `uvicorn` (ASGI server), `pydantic` (message/data validation), `textual` (existing TUI mode), `marked` (browser Markdown renderer), `alpinejs` (minimal reactive UI shell)  
**Storage**: Existing local file-backed state reused for session persistence; Docker mount at `/data`; in-memory `SessionRegistry` for active connections  
**Testing**: `pytest`, FastAPI/Starlette `TestClient` for HTTP/WebSocket integration tests, existing contract tests, `ruff`, `ty`  
**Target Platform**: Localhost development on Linux/macOS and single-container Docker deployment on personal machines/home servers  
**Project Type**: Single Python application with dual interfaces: TUI + web server  
**Performance Goals**: First onboarding message visible within 2 seconds on localhost; reconnect recovers an in-flight session without page reload; Docker service healthy within 30 seconds  
**Constraints**: No Node.js build step at runtime; one active WebSocket session per session ID; static assets served by the Python app; TUI remains the default mode; single-user/self-hosted installation  
**Scale/Scope**: One learner per installation, one active browser session per cookie, tiny static asset bundle, low request volume, no multi-tenant auth

## Constitution Check

*Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Test-First | **Required** | Start with failing contract/integration tests for `ApiMediator`, HTTP routing, reconnect behavior, and session-conflict handling before implementation |
| II. Evidence-Based Validation | **Required** | Validate with a real browser flow plus HTTP/WebSocket integration tests using realistic session restore and disconnect scenarios |
| III. DRY | **Watch** | Shared `IOMediator` semantics must stay centralized; TUI- and web-specific rendering logic may diverge, but message envelope creation should live in one place |
| IV. YAGNI | **Gate passed** | No SPA build chain, no separate frontend project, no auth subsystem, no database migration layer, no SSE fallback in v2 |
| V. Provider Interface | **Gate passed** | `ApiMediator` remains an `IOMediator` implementation; external browser transport stays behind that interface and does not leak into state handlers |

No constitutional violations identified. Complexity Tracking remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/v2-web-ui/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── http_routes.md
│   └── websocket_messages.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
└── milai/
    ├── main.py                       # mode selection: tui (default) or web
    ├── io/
    │   ├── mediator.py               # existing IOMediator protocol
    │   ├── types.py                  # existing RichContent / Choice / ContentKind
    │   ├── tui/
    │   │   └── app.py                # existing TextualMediator
    │   └── web/
    │       ├── app.py                # FastAPI app factory, routes, cookie issuance
    │       ├── mediator.py           # ApiMediator implementation
    │       ├── messages.py           # Pydantic message envelopes
    │       ├── sessions.py           # SessionRegistry + reconnect/session-conflict logic
    │       └── static/
    │           ├── index.html
    │           ├── app.js
    │           ├── app.css
    │           └── vendor/           # vendored marked/alpine for offline Docker use
    ├── storage/
    │   └── ...                       # existing local state persistence, reused
    ├── state/
    │   └── ...                       # existing state machine, unchanged
    └── llm/
        └── ...                       # existing provider interface + implementation, unchanged

tests/
├── contract/
│   └── test_io_mediator.py           # extend to assert ApiMediator conformance
├── integration/
│   ├── test_web_http.py              # GET /, static assets, health route, cookie issuance
│   └── test_websocket_session.py     # prompt/choose/confirm roundtrip, reconnect, conflict
└── unit/
    └── test_web_messages.py          # envelope validation / serialization
```

**Structure Decision**: Keep a single Python project under `src/milai`. The web UI is not a separate frontend app; it is a thin static client co-located with the backend under `src/milai/io/web/static/`. This matches the spec constraint of no Node runtime and keeps the architecture additive to the existing TUI mediator pattern.

## Design Decisions Summary

| Decision | Choice | Key reason |
|---|---|---|
| Backend framework | FastAPI | Native WebSocket support, static file serving, idiomatic Python, direct fit for `ApiMediator` |
| Frontend style | Static HTML/CSS/JS + Alpine.js + Marked.js | Small surface area, no build chain, enough interactivity for chat + buttons + progress |
| Browser transport | WebSocket | Bidirectional by design; simpler than SSE + extra POST endpoints |
| Session persistence | Persistent cookie + file-backed state + in-memory registry | Matches resume/reconnect requirements without introducing accounts or a DB |
| Deployment | Single Docker image running Uvicorn | Simplest deployment shape for self-hosted single-user app |
| TUI compatibility | Preserve `TextualMediator`; add `--mode web` | v2 is additive, not a rewrite |

## Phase Outputs

Phase 0 research is captured in [research.md](research.md). Phase 1 design artifacts are [data-model.md](data-model.md), [quickstart.md](quickstart.md), and the HTTP/WebSocket contracts under [contracts/](contracts/).

## Complexity Tracking

No justified violations required.
