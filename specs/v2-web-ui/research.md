# Research: v2 Web UI

**Branch**: `v2-web-ui` | **Date**: 2026-04-25

---

## Decision 1: Use FastAPI as the Backend Framework

**Decision**: Use FastAPI for the v2 web backend, with Uvicorn as the ASGI server.

**Rationale**:

This feature is not "build a quick web demo". It is "add a browser transport to an existing asynchronous state-machine application without changing the core workflow." The backend needs to:

- expose a normal HTTP entrypoint for `GET /`
- serve static assets directly
- hold a long-lived bidirectional connection per browser session
- enforce "one active connection per session ID"
- reconnect cleanly after a dropped socket
- map browser events to the existing `IOMediator` contract

FastAPI matches that directly. Its official docs cover both static file mounting and first-class WebSocket endpoints, which are the two primitives this feature needs most:

- FastAPI Static Files: <https://fastapi.tiangolo.com/tutorial/static-files/>
- FastAPI WebSockets: <https://fastapi.tiangolo.com/advanced/websockets/>

FastAPI is also the right complexity level for a Python-first codebase. It does not force a new execution model over the app. The state machine remains the source of truth; FastAPI only hosts the transport adapter.

**Alternatives considered**:

- **Plain Starlette**: technically sufficient, but FastAPI adds better validation and clearer dependency ergonomics with almost no extra conceptual cost.
- **Django / Flask**: rejected as a poorer fit for async WebSocket-first work in this small single-process app.

---

## Decision 2: Do Not Use Streamlit

**Decision**: Do not use Streamlit for v2.

**Rationale**:

Streamlit is good when the framework owns the page lifecycle and your app is mostly "render widgets from Python state." That is not milai's shape. milai already has its own workflow engine and mediator contract.

The decisive mismatch is session behavior. Streamlit's docs explicitly note that Session State is tied to a WebSocket connection and is reset when the browser tab reloads; they also note that Session State is not persisted if the server crashes:

- Streamlit Session State: <https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state>
- Streamlit architecture/session state: <https://docs.streamlit.io/develop/concepts/architecture/session-state>

That conflicts with the spec, which requires:

- session resume after tab close/reopen
- reconnect behavior without page reload
- file-backed persistent state independent of the browser connection

Streamlit also pushes you toward a rerun-oriented widget model. That is workable for prototypes, but awkward for an existing `show/prompt/choose/confirm` mediator interface. You would end up adapting milai to Streamlit instead of adapting the browser to milai.

**Alternatives considered**:

- **Streamlit chat elements** (`st.chat_message`, `st.chat_input`): useful for fast demos, but still live inside Streamlit's rerun/session model and do not solve the session persistence mismatch.
- **Streamlit custom components**: possible, but then you are effectively building a custom frontend inside another app framework, which adds a layer without reducing the hard parts.

---

## Decision 3: Do Not Use Gradio

**Decision**: Do not use Gradio for v2.

**Rationale**:

Gradio is strong for ML demos and event-driven UI flows where the framework dispatches Python functions for each interaction. milai is different: it already owns the conversation loop and needs explicit transport-level control.

The same fundamental session mismatch appears here. Gradio's `State` docs note that browser refresh or tab close clears state, and its session state is scoped to Gradio's app session model:

- Gradio State: <https://www.gradio.app/docs/gradio/state>
- Gradio Blocks / queue / launch docs: <https://www.gradio.app/docs/gradio/blocks>

Gradio is also a tell here: its own `Blocks.launch()` exposes `app_kwargs` for the underlying FastAPI app. That is useful, but it reinforces the point that once you need custom session cookies, explicit WebSocket contracts, and mediator-driven control flow, you are already near the level where using FastAPI directly is the simpler design.

Gradio's queueing and high-level chat abstractions are not a benefit for this feature. They would introduce framework-specific execution semantics around a backend that already has its own orchestration model.

**Alternatives considered**:

- **Gradio `ChatInterface` / `Blocks`**: fast for proof-of-concept chat apps, but too opinionated for reconnect semantics, custom typed command envelopes, and incremental mediator-driven UI state.

---

## Decision 4: Use a Thin Static Frontend, Not a Separate SPA

**Decision**: Build the frontend as static HTML/CSS/JS served by FastAPI, with Alpine.js for light UI state and Marked.js for Markdown rendering.

**Rationale**:

The spec already constrains runtime to "no Node.js build step" and says the browser UI only needs:

- chat transcript rendering
- prompt input
- choice buttons
- confirm buttons
- progress rendering
- connection/reconnect indicator

That is a small UI surface. A React/Vue/Vite stack would add a build chain and more moving pieces than the feature needs. Alpine.js is enough for local reactive state such as message list, pending request, and connection status. Marked.js handles Markdown rendering cleanly in-browser.

This choice keeps the feature learnable for a developer who is new to web work: the frontend is plain browser technology, not a full SPA toolchain.

**Alternatives considered**:

- **React/Vue/Svelte SPA**: powerful, but rejected under YAGNI for this feature size and the runtime/build constraints.
- **Pure vanilla JS with no helper library**: possible, but Alpine.js is a small enough convenience layer to simplify the DOM update logic without introducing a build system.

---

## Decision 5: Use WebSockets, Not SSE

**Decision**: Use a single WebSocket endpoint as the primary browser transport.

**Rationale**:

`IOMediator` is fundamentally bidirectional. The backend sends display commands and input requests; the browser sends input responses. WebSockets model that directly.

SSE would only solve server-to-client streaming. The client-to-server half would then need extra `POST` endpoints for prompt/choice/confirm responses, plus correlation IDs across two transports. That is more surface area and more failure modes for no user-visible gain.

WebSockets also align with the reconnect requirement: one socket per active browser session, explicit disconnect detection, and explicit `session_conflict` handling.

**Alternatives considered**:

- **SSE + REST POST**: rejected as strictly more complex for this interaction model.

---

## Decision 6: Session Persistence Model

**Decision**: Persist the learner/app state using the existing file-backed storage and track active browser connections with an in-memory `SessionRegistry`; issue a persistent `milai_session` cookie holding an opaque UUID.

**Rationale**:

This is the minimal design that satisfies the spec:

- file-backed app state survives tab close/reopen and container restart
- cookie identifies the browser session across reconnects
- in-memory registry prevents concurrent active sockets for the same session ID
- no auth/accounts/database required

The cookie does not become the source of truth; it is only the lookup key for the persisted state plus active-connection bookkeeping.

**Alternatives considered**:

- **Database-backed session table**: rejected as unnecessary for single-user self-hosted v2.
- **Browser-local-only state**: rejected because it fails container restart and server-side resume requirements.

---

## Recommendation Summary

If the goal is to learn "real web" while still landing this feature cleanly, the right path is:

1. FastAPI backend
2. plain static frontend served by that backend
3. one typed WebSocket protocol between them

That teaches the core web concepts directly: HTTP routing, cookies, static assets, WebSockets, browser state, and deployment. Streamlit and Gradio would be faster for a throwaway demo, but they would hide or distort the exact parts of web architecture this feature actually depends on.
