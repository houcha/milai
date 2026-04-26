# Data Model: v2 Web UI

**Branch**: `v2-web-ui` | **Date**: 2026-04-25

---

## Overview

v2 does **not** replace the existing learning data model. `UserState` and `AppState` remain the canonical persisted workflow/domain structures from v1. The v1 TUI may be removed, but the web feature still adds transport-layer entities around the learning model instead of embedding browser concerns into it:

- a persistent browser session identifier
- an active connection registry
- typed WebSocket command/response envelopes
- a small amount of in-flight mediator request state

The important boundary is:

- **Persisted learning state** remains in the existing storage layer
- **Active browser connection state** remains transient and in-memory

---

## Reused Existing Models

The following models are consumed by the web layer as-is:

- `UserState`
- `AppState`
- `RichContent`
- `Choice`
- `ContentKind`

`ApiMediator` translates these interaction types into browser-facing message envelopes.

---

## BrowserSession

Represents a durable browser identity across reconnects.

```text
BrowserSession
├── session_id: str               # UUID stored in persistent cookie
├── created_at: datetime
├── last_seen_at: datetime
└── storage_key: str              # lookup key for persisted app/user state
```

**Rules**:

- `session_id` is opaque to the client.
- The session cookie survives tab close/reopen.
- A reconnect with the same `session_id` resumes the same persisted state.

---

## SessionRegistryEntry

In-memory record for the currently active WebSocket connection, if any.

```text
SessionRegistryEntry
├── session_id: str
├── connection_id: str            # UUID for the specific socket connection
├── status: str                   # "connected" | "reconnecting" | "closed"
├── connected_at: datetime
├── last_message_at: datetime
└── pending_request_id: str | None
```

**Rules**:

- At most one `connected` entry may exist per `session_id`.
- If a second socket connects with the same `session_id`, the new socket receives `session_conflict` and is closed.
- `pending_request_id` tracks whether the mediator is waiting for a browser response.

---

## ServerMessage Envelope

All WebSocket messages from server to browser share a common top-level shape:

```json
{
  "type": "prompt",
  "request_id": "req_123",
  "payload": {}
}
```

```text
ServerMessage
├── type: str
├── request_id: str | None
└── payload: object
```

### Server message variants

```text
hello
├── session_id: str
├── resumed: bool
└── mode: "web"

show
├── content.kind: "text" | "markdown" | "header" | "progress"
├── content.text: str
├── content.current: int | None
└── content.total: int | None

prompt
├── label: str
└── placeholder: str

choose
├── label: str
└── choices: list[{label, value, description}]

confirm
└── label: str

clear
└── {}

error
└── message: str

connection_status
├── state: "connected" | "reconnecting"
└── detail: str | None

session_conflict
└── message: str
```

**Rules**:

- Interactive messages (`prompt`, `choose`, `confirm`) must include `request_id`.
- Display-only messages (`show`, `clear`, `error`, `connection_status`) do not require a reply.

---

## ClientMessage Envelope

All browser-to-server messages share the same top-level shape:

```json
{
  "type": "prompt_response",
  "request_id": "req_123",
  "payload": {}
}
```

```text
ClientMessage
├── type: str
├── request_id: str | None
└── payload: object
```

### Client message variants

```text
ready
└── {}

prompt_response
└── value: str

choose_response
└── value: str

confirm_response
└── value: bool

ping
└── sent_at: str
```

**Rules**:

- Response messages must echo the `request_id` sent by the server.
- A client response for an unknown or expired `request_id` is ignored and logged.

---

## ApiMediator Pending Request

Transient mediator state used to map an interaction-boundary call to the eventual browser response.

```text
PendingRequest
├── request_id: str
├── kind: str                      # "prompt" | "choose" | "confirm"
├── created_at: datetime
└── resolver: Future[Any]
```

**Rules**:

- Only one interactive request may be pending per active session at a time.
- The pending request is cleared on successful reply or socket termination.
- On disconnect, the request remains logically outstanding until the same session reconnects or the server aborts it.

---

## Frontend View State

Ephemeral browser-side state held in Alpine.js.

```text
FrontendState
├── messages: list[RenderedMessage]
├── connection_state: "connecting" | "connected" | "reconnecting" | "conflict"
├── pending_request: PendingUiRequest | None
└── session_ready: bool
```

```text
RenderedMessage
├── role: "system" | "assistant" | "error"
├── kind: "text" | "markdown" | "header" | "progress"
├── text: str
├── current: int | None
└── total: int | None
```

```text
PendingUiRequest
├── request_id: str
├── kind: "prompt" | "choose" | "confirm"
├── label: str
├── placeholder: str | None
└── choices: list[Choice] | None
```

This state is disposable. On page reload, it is reconstructed from the resumed session plus new server messages.

---

## State Transitions

### Connection lifecycle

```text
new browser visit
→ cookie missing? issue session_id
→ open websocket
→ register SessionRegistryEntry(status="connected")
→ send hello(resumed=bool)
→ replay current app surface by continuing the state machine
```

### Disconnect / reconnect

```text
socket drop
→ registry status = "reconnecting"
→ frontend shows reconnecting indicator
→ browser reconnects with same cookie
→ old connection record replaced
→ pending request and persisted app state resume
```

### Conflict

```text
second socket for same session_id while first is active
→ send session_conflict
→ close second socket
```

---

## Validation Rules

- `session_id` and `connection_id` are UUID strings.
- `request_id` is required for all interactive request/response pairs.
- `choose_response.value` must match one of the offered choice values for that `request_id`.
- `confirm_response.value` must be a strict boolean.
- `show` with `kind="progress"` must include both `current` and `total`.

---

## Persistence Boundary

Persisted:

- existing `UserState`
- existing `AppState`
- cookie value in the browser

Transient:

- `SessionRegistryEntry`
- `PendingRequest`
- browser `FrontendState`

That separation is intentional. Losing a socket must not lose the learner's progress.
