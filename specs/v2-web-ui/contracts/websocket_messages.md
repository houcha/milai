# Contract: WebSocket Messages

**Feature**: `v2-web-ui`
**Endpoint**: `/ws`
**Purpose**: Define the typed message protocol between browser UI and `ApiMediator`.

---

## Connection Rules

- Browser connects to `/ws` using the `milai_session` cookie set by `GET /`.
- Server allows at most one active socket per `milai_session`.
- A duplicate connection for the same session receives `session_conflict` and is closed.

---

## Message Envelope

All messages are JSON objects with this shape:

```json
{
  "type": "prompt",
  "request_id": "req_123",
  "payload": {}
}
```

Fields:

- `type`: required string discriminator
- `request_id`: nullable correlation ID; required for interactive request/response pairs
- `payload`: required object

---

## Server → Client Messages

### `hello`

```json
{
  "type": "hello",
  "request_id": null,
  "payload": {
    "session_id": "uuid",
    "resumed": true,
    "mode": "web"
  }
}
```

Sent immediately after successful socket registration.

---

### `show`

```json
{
  "type": "show",
  "request_id": null,
  "payload": {
    "kind": "markdown",
    "text": "# Welcome",
    "current": null,
    "total": null
  }
}
```

Maps from `IOMediator.show()`.

For progress rendering:

```json
{
  "kind": "progress",
  "text": "Lesson 2 of 5",
  "current": 2,
  "total": 5
}
```

---

### `prompt`

```json
{
  "type": "prompt",
  "request_id": "req_prompt_1",
  "payload": {
    "label": "What language do you want to learn?",
    "placeholder": "e.g. Spanish"
  }
}
```

Maps from `IOMediator.prompt()`.

---

### `choose`

```json
{
  "type": "choose",
  "request_id": "req_choose_1",
  "payload": {
    "label": "Pick one",
    "choices": [
      {"label": "Beginner", "value": "beginner", "description": ""},
      {"label": "Intermediate", "value": "intermediate", "description": ""}
    ]
  }
}
```

Maps from `IOMediator.choose()`.

---

### `confirm`

```json
{
  "type": "confirm",
  "request_id": "req_confirm_1",
  "payload": {
    "label": "Continue?"
  }
}
```

Maps from `IOMediator.confirm()`.

---

### `clear`

```json
{
  "type": "clear",
  "request_id": null,
  "payload": {}
}
```

Maps from `IOMediator.clear()`.

---

### `error`

```json
{
  "type": "error",
  "request_id": null,
  "payload": {
    "message": "Connection lost"
  }
}
```

Maps from `IOMediator.show_error()`.

---

### `connection_status`

```json
{
  "type": "connection_status",
  "request_id": null,
  "payload": {
    "state": "reconnecting",
    "detail": "Trying again..."
  }
}
```

Used for transient frontend UI state.

---

### `session_conflict`

```json
{
  "type": "session_conflict",
  "request_id": null,
  "payload": {
    "message": "Another browser is already connected for this session."
  }
}
```

Client must display the message and stop reconnect attempts for that socket.

---

## Client → Server Messages

### `ready`

```json
{
  "type": "ready",
  "request_id": null,
  "payload": {}
}
```

Signals the client has mounted and can receive the current surface.

---

### `prompt_response`

```json
{
  "type": "prompt_response",
  "request_id": "req_prompt_1",
  "payload": {
    "value": "Spanish"
  }
}
```

---

### `choose_response`

```json
{
  "type": "choose_response",
  "request_id": "req_choose_1",
  "payload": {
    "value": "beginner"
  }
}
```

`value` must match one of the offered choice values for that `request_id`.

---

### `confirm_response`

```json
{
  "type": "confirm_response",
  "request_id": "req_confirm_1",
  "payload": {
    "value": true
  }
}
```

`value` must be a strict boolean.

---

### `ping`

```json
{
  "type": "ping",
  "request_id": null,
  "payload": {
    "sent_at": "2026-04-25T12:00:00Z"
  }
}
```

Optional keepalive/diagnostic message.

---

## Validation Rules

- Unknown `type` values are rejected and logged.
- Interactive server messages must include `request_id`.
- Interactive client responses without matching pending `request_id` are ignored and logged.
- Message payloads must validate against their schema before dispatch.
