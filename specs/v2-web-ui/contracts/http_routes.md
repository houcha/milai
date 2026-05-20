# Contract: HTTP Routes

**Feature**: `v2-web-ui`
**Purpose**: Define the browser-facing HTTP surface for milai web mode.

---

## Routes

### `GET /`

Serve the main HTML shell for the web UI.

**Behavior**:

- returns `200 text/html`
- if the `milai_session` cookie is missing, issue a new persistent cookie with an opaque UUID value
- HTML bootstraps the static app and opens the WebSocket connection to `/ws`

**Response headers**:

- `Set-Cookie: milai_session=<uuid>; HttpOnly; SameSite=Lax; Path=/`

---

### `GET /assets/{path}`

Serve static assets used by the web UI.

**Behavior**:

- returns `200` for known assets
- returns `404` for unknown asset paths
- serves `app.js`, `app.css`, and vendored browser libraries

---

### `GET /healthz`

Health endpoint for Docker/runtime checks.

**Behavior**:

- returns `200 application/json`
- body shape:

```json
{
  "status": "ok"
}
```

This route must not require a session cookie.

---

## Cookie Contract

### Cookie name

`milai_session`

### Value

Opaque UUID string.

### Attributes

- `HttpOnly`
- `SameSite=Lax`
- `Path=/`

`Secure` may be added when HTTPS termination exists, but is not required for localhost development.

---

## Error Semantics

- `GET /` should fail only on server-side fatal errors and should return `500` in that case.
- `GET /assets/{path}` returns `404` for missing assets.
- `GET /healthz` returns `503` only if startup dependencies required for serving are unavailable.
