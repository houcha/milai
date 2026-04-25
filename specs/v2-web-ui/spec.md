# Feature Specification: v2 — Web UI

**Feature Branch**: `v2-web-ui`
**Created**: 2026-04-25
**Status**: Draft
**Input**: User description: "Create a plan for v2, describe how we will switch from TUI to web UI." Deferred from v1: "ApiMediator (FastAPI + WebSocket/SSE) and Docker packaging — v2".

## Context

v1 (`001-ai-language-learning`) delivered a fully working TUI application where all user-facing I/O is mediated through the `IOMediator` protocol (`milai/io/mediator.py`). The architecture was explicitly designed for this migration: `TextualMediator` is the v1 concrete implementation; v2 adds `ApiMediator` alongside it. The state machine, handlers, data model, LLM client, storage client, and SRS subsystem are unchanged.

## Clarifications

### Session 2026-04-25

- Q: Should the spec explicitly mention FastAPI, or should the concrete tech stack be introduced at plan level? → A: Keep protocol-level requirements in the spec, but move `FastAPI` itself to the plan.

## User Scenarios & Testing

### User Story 1 - Start a session from a browser (Priority: P1)

A user opens `http://localhost:8000` in a browser. The milai chat interface loads and the onboarding flow begins automatically — the same conversation flow as v1 TUI, rendered in the browser.

**Why this priority**: This is the core feature of v2. All other stories depend on this foundation.

**Independent Test**: Can be fully tested by navigating to localhost, completing the onboarding prompt, and receiving the first assessment question — confirming the state machine drives the browser UI exactly as it does the TUI.

**Acceptance Scenarios**:

1. **Given** the milai server running locally or in Docker, **When** the user navigates to the root URL, **Then** the chat interface loads and the first onboarding message appears within 2 seconds.
2. **Given** a session in progress, **When** the user closes and reopens the browser tab, **Then** the session resumes from the last saved state (same checkpoint, no progress lost).
3. **Given** an active session, **When** the WebSocket connection drops, **Then** the UI shows a reconnecting indicator and automatically reconnects without requiring a page reload.

---

### User Story 2 - Interact with the full learning flow in the browser (Priority: P1)

All interactions available in the TUI — free-text input, choice selection, confirm dialogs, progress updates — are available as native browser controls. Markdown content (theory explanations) renders with formatting.

**Why this priority**: Without full interaction parity, the web UI cannot replace the TUI for any real learning session.

**Independent Test**: Can be fully tested by driving a complete lesson — starting from a pre-populated `UserState` — through theory display, exercise completion, deviation, and return, entirely in the browser.

**Acceptance Scenarios**:

1. **Given** a `show(RichContent(kind=MARKDOWN))` call from the state machine, **When** it arrives at the frontend, **Then** it is rendered as formatted HTML (headings, bold, lists, code).
2. **Given** a `choose(label, choices)` call, **When** it arrives at the frontend, **Then** it is rendered as a list of clickable buttons; selecting one sends the choice back over the WebSocket.
3. **Given** a `prompt(label)` call, **When** it arrives at the frontend, **Then** a text input is shown; submitting it sends the text back over the WebSocket.
4. **Given** a `confirm(label)` call, **When** it arrives at the frontend, **Then** Yes/No buttons are shown; selecting one sends the boolean back.
5. **Given** a `show(RichContent(kind=PROGRESS))` call, **When** it arrives at the frontend, **Then** a progress bar or fraction indicator is rendered.

---

### User Story 3 - Docker deployment (Priority: P2)

The entire application — backend + frontend static assets — ships as a single Docker image with a simple `docker run` command. State persists to a mounted volume.

**Why this priority**: Docker is the primary deployment target for v2. Without it, the web UI is development-only.

**Independent Test**: Can be fully tested by building the Docker image from the repository, running it with a volume mount, completing an onboarding flow, restarting the container, and confirming the session resumes.

**Acceptance Scenarios**:

1. **Given** the Docker image built from the repository, **When** run with `docker run -p 8000:8000 -v ~/.milai:/data milai`, **Then** the application is accessible at `http://localhost:8000`.
2. **Given** a mounted data volume, **When** the container is restarted, **Then** prior session state is preserved and the browser can resume from the same checkpoint.
3. **Given** `docker-compose up`, **When** the stack starts, **Then** the service is healthy and accessible at `http://localhost:8000` within 30 seconds.

---

### User Story 4 - TUI remains functional (Priority: P2)

The `milai` command continues to work in TUI mode. The web UI is additive — it does not remove or break the existing TUI entrypoint.

**Why this priority**: The TUI is an existing, working interface. Regression is unacceptable.

**Acceptance Scenarios**:

1. **Given** `milai --mode tui` (or no `--mode` flag), **When** executed in a terminal, **Then** the Textual TUI launches exactly as in v1 with no behaviour change.
2. **Given** `milai --mode web`, **When** executed, **Then** the web server starts and serves the web UI.

---

## Requirements

### Functional Requirements

- **FR-001**: The web application MUST implement the `IOMediator` protocol via `ApiMediator` over a WebSocket-based browser connection. The state machine and all handlers MUST run unchanged.
- **FR-002**: Session state MUST be preserved across browser tab close/reopen for the duration of the installation's active session (persistent cookie + file-backed state).
- **FR-003**: The frontend MUST render `RichContent` with `ContentKind.MARKDOWN` using a Markdown renderer.
- **FR-004**: The frontend MUST present `choose()` as interactive buttons and `confirm()` as Yes/No buttons.
- **FR-005**: The frontend MUST show a connection status indicator and automatically reconnect on WebSocket drop.
- **FR-006**: The application MUST be packaged as a Docker image; state MUST persist to a mounted volume (`/data` inside the container).
- **FR-007**: The TUI entrypoint MUST remain functional. Running `milai` without `--mode web` MUST launch the TUI.
- **FR-008**: `ApiMediator` MUST satisfy the existing `IOMediator` protocol; the contract test (`tests/contract/test_io_mediator.py`) MUST pass for `ApiMediator`.
- **FR-009**: Only one active WebSocket session per session ID is permitted. A second connection with the same session ID MUST receive a `session_conflict` message and be closed.

### Non-Functional Requirements

- **NFR-001**: First message visible in browser within 2 seconds after page load on localhost.
- **NFR-002**: No Node.js build step required at runtime; frontend assets are pure HTML/CSS/JS served directly as static files.
- **NFR-003**: Total Docker image size < 500 MB.
- **NFR-004**: All existing tests (unit, integration, contract) MUST continue to pass without modification.
- **NFR-005**: The feature spec defines externally visible behavior and transport constraints; the concrete backend framework is selected in the implementation plan.

---

## Key Entities (new for v2)

- **WebSocket session**: A single active browser conversation; identified by a persistent cookie containing a UUID session token. One session per installation at a time.
- **ApiMediator**: Concrete implementation of `IOMediator` over the browser-facing WebSocket transport selected for v2.
- **WebSocket message**: Typed JSON envelope sent between backend and frontend. Server-to-client messages are display commands and input requests; client-to-server messages are input responses.
- **SessionRegistry**: In-memory registry tracking active WebSocket connections to prevent concurrent session conflicts.

---

## Assumptions

- Single user per installation — same as v1. The web UI serves one active session at a time. A second browser with the same session cookie joins the same session; a different session cookie starts a fresh session (up to the single-session limit).
- The application is self-hosted (Docker on a personal machine or home server). No cloud deployment, no external auth, no user accounts.
- The TUI entrypoint remains usable via `--mode tui`.
- The frontend is served as static files directly by the selected backend web server; no CDN or separate static server is needed for the HTML shell (Alpine.js and Marked.js are loaded from CDN on first visit; vendored copies for offline Docker use).
- Markdown rendering is the only rich display format needed for v2; no audio, images, or video.
- `LLMClient` and `StorageClient` are unchanged from v1.

---

## Success Criteria

- **SC-001**: All existing v1 tests pass without modification after v2 is added.
- **SC-002**: The `IOMediator` contract test passes for `ApiMediator`.
- **SC-003**: A full onboarding → assessment → curriculum → lesson flow can be completed in the browser.
- **SC-004**: Session state survives a browser tab close/reopen and a container restart.
- **SC-005**: `docker-compose up` starts the application accessible at `http://localhost:8000`.
- **SC-006**: `milai --mode tui` continues to launch the Textual TUI with no regression.
