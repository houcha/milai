# Implementation Plan: v2 Web UI

**Branch**: `v2-web-ui` | **Date**: 2026-04-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/v2-web-ui/spec.md`

## Summary

Add the browser UI as the product interface without coupling the learning engine to web transport concerns. The selected implementation is a single Python web process built on FastAPI + Uvicorn, serving a small static frontend (HTML/CSS/JS with Alpine.js and Marked.js) and a WebSocket endpoint that backs `ApiMediator`. The existing state machine, handlers, SRS, and provider interfaces remain web-framework independent; v2 may remove or deprecate the temporary Textual TUI.

The key architectural choice is to use FastAPI directly rather than Streamlit or Gradio. This feature needs explicit control over WebSocket lifecycle, persistent session cookies, reconnect behavior, and a thin translation layer from interaction-boundary calls to browser messages. FastAPI fits that shape directly. Streamlit and Gradio are productive when the framework owns the app flow, but here the app flow is already owned by milai's state machine.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: `fastapi` (ASGI app + WebSockets + static files), `uvicorn` (ASGI server), `pydantic` (message/data validation), `marked` (browser Markdown renderer), `alpinejs` (minimal reactive UI shell)
**Storage**: Existing local file-backed `PersistedState` snapshot reused for session persistence; Docker mount at `/data`; in-memory `SessionRegistry` for active connections  
**Testing**: `pytest`, FastAPI/Starlette `TestClient` for HTTP/WebSocket integration tests, existing contract tests, `ruff`, `ty`  
**Target Platform**: Localhost development on Linux/macOS and single-container Docker deployment on personal machines/home servers  
**Project Type**: Single Python web application with a browser interface
**Performance Goals**: First onboarding message visible within 2 seconds on localhost; reconnect recovers an in-flight session without page reload; Docker service healthy within 30 seconds  
**Constraints**: No Node.js build step at runtime; one active WebSocket session per session ID; static assets served by the Python app; single-user/self-hosted installation; no requirement to preserve the v1 terminal UI
**Scale/Scope**: One learner per installation, one active browser session per cookie, tiny static asset bundle, low request volume, no multi-tenant auth

## Constitution Check

*Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Test-First | **Required** | Start with failing contract/integration tests for `ApiMediator`, HTTP routing, reconnect behavior, and session-conflict handling before implementation |
| II. Evidence-Based Validation | **Required** | Validate with a real browser flow plus HTTP/WebSocket integration tests using realistic session restore and disconnect scenarios |
| III. DRY | **Watch** | Shared interaction semantics must stay centralized; browser rendering and WebSocket message envelope creation should stay in the web adapter |
| IV. YAGNI | **Gate passed** | No SPA build chain, no separate frontend project, no auth subsystem, no database migration layer, no SSE fallback in v2 |
| V. Provider Interface | **Gate passed** | `ApiMediator` implements the narrow interaction boundary; external browser transport stays behind that boundary and does not leak into state handlers |

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
    ├── main.py                       # web server entrypoint
    ├── io/
    │   ├── mediator.py               # existing IOMediator protocol
    │   ├── types.py                  # existing RichContent / Choice / ContentKind
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
│   └── test_io_mediator.py           # assert ApiMediator and test double satisfy the interaction contract
├── integration/
│   ├── test_web_http.py              # GET /, static assets, health route, cookie issuance
│   └── test_websocket_session.py     # prompt/choose/confirm roundtrip, reconnect, conflict
└── unit/
    └── test_web_messages.py          # envelope validation / serialization
```

**Structure Decision**: Keep a single Python project under `src/milai`. The web UI is not a separate frontend app; it is a thin static client co-located with the backend under `src/milai/io/web/static/`. This matches the spec constraint of no Node runtime and keeps browser transport concerns outside the learning engine.

## Design Decisions Summary

| Decision | Choice | Key reason |
|---|---|---|
| Backend framework | FastAPI | Native WebSocket support, static file serving, idiomatic Python, direct fit for `ApiMediator` |
| Frontend style | Static HTML/CSS/JS + Alpine.js + Marked.js | Small surface area, no build chain, enough interactivity for chat + buttons + progress |
| Browser transport | WebSocket | Bidirectional by design; simpler than SSE + extra POST endpoints |
| Session persistence | Persistent cookie + file-backed `PersistedState` snapshot + in-memory registry | Matches resume/reconnect requirements without introducing accounts or a DB |
| Deployment | Single Docker image running Uvicorn | Simplest deployment shape for self-hosted single-user app |
| TUI lifecycle | Remove or deprecate `TextualMediator` in v2 | The TUI was scaffolding; v2 should optimize around the browser product UI |

## Phase Outputs

Phase 0 research is captured in [research.md](research.md). Phase 1 design artifacts are [data-model.md](data-model.md), [quickstart.md](quickstart.md), and the HTTP/WebSocket contracts under [contracts/](contracts/).

## Complexity Tracking

No justified violations required.
