# Quickstart: v2 Web UI

**Branch**: `v2-web-ui` | **Date**: 2026-04-25

---

## Goal

Run milai as a local web application and in Docker.

This document describes the intended developer workflow for the v2 implementation.

---

## Prerequisites

- Python 3.12+
- `uv`
- Docker (for container validation)
- An API key for your selected LLM provider

---

## Dependencies

Expected Python dependencies for v2:

- `fastapi`
- `uvicorn`
- existing project/runtime dependencies

Frontend dependencies are served as static assets. No Node.js runtime build step is required.

---

## Local Setup

```bash
cd /home/bail/Code/milai
uv sync
export GEMINI_API_KEY="your-key-here"
```

If you are using a different provider, export the matching provider key instead.

---

## Run the Web UI

```bash
uv run milai --host 127.0.0.1 --port 8000
```

Open <http://localhost:8000>.

Expected behavior:

1. Browser loads the chat shell.
2. A persistent session cookie is issued if one does not already exist.
3. The browser opens a WebSocket connection.
4. The onboarding flow starts or resumes from the last saved checkpoint.

---

## Docker Run

```bash
docker build -t milai .
docker run --rm -p 8000:8000 -v "$HOME/.milai:/data" milai
```

Expected behavior:

- app is reachable at <http://localhost:8000>
- learner state persists under the mounted host volume
- restarting the container preserves progress

---

## Verification

### HTTP and asset checks

```bash
uv run pytest tests/integration/test_web_http.py
```

### WebSocket and reconnect checks

```bash
uv run pytest tests/integration/test_websocket_session.py
```

### Contract checks

```bash
uv run pytest tests/contract/test_io_mediator.py
```

This verifies the web mediator and scripted test double satisfy the interaction boundary used by the learning handlers.

### Full QA

```bash
just qa
```

---

## Manual End-to-End Validation

1. Start `milai`.
2. Complete onboarding in the browser.
3. Close the tab.
4. Re-open `http://localhost:8000`.
5. Confirm the session resumes from the previous checkpoint.
6. Refresh or temporarily interrupt the socket and confirm the reconnect indicator appears, then clears automatically.
7. Restart the container and confirm progress still exists.
