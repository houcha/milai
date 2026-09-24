"""Dependency-free local web interface for conversation and learning state."""

import asyncio
import json
from contextlib import suppress
from importlib.resources import files
from urllib.parse import urlsplit

from openai import APITimeoutError, RateLimitError

from milai.config import Settings
from milai.observability import Telemetry
from milai.store import Store
from milai.tutor import Tutor

HOST = "127.0.0.1"
MAX_HEADER_BYTES = 32_768
MAX_BODY_BYTES = 16_384


def learning_view(snapshot: dict) -> dict:
    """Project normalized storage into the learner-facing learning-map contract."""
    profile = {
        field: record.get("value")
        for field, record in snapshot["profile"].items()
        if record.get("value")
    }
    return {
        "profile": profile,
        "topics": snapshot.get("topics", []),
        "focus": snapshot.get("focus"),
        "skills": snapshot.get("skills", []),
    }


class WebApplication:
    """Serve one local learner's sessions, chat, and exercise actions over HTTP."""

    def __init__(self, store: Store, tutor: Tutor, session: str, port: int):
        """Bind the app to a store, tutor, selected session, and local port."""
        self.store = store
        self.tutor = tutor
        self.learner = store.owner
        self.session = session
        self.port = port
        self.lock = asyncio.Lock()
        asset_root = files("milai").joinpath("web")
        self.assets = {
            "/": ("text/html; charset=utf-8", asset_root.joinpath("index.html")),
            "/styles.css": (
                "text/css; charset=utf-8",
                asset_root.joinpath("styles.css"),
            ),
            "/app.js": (
                "text/javascript; charset=utf-8",
                asset_root.joinpath("app.js"),
            ),
            "/exercise-controller.js": (
                "text/javascript; charset=utf-8",
                asset_root.joinpath("exercise-controller.js"),
            ),
            "/markdown.bundle.js": (
                "text/javascript; charset=utf-8",
                asset_root.joinpath("markdown.bundle.js"),
            ),
        }

    def bootstrap(self) -> dict:
        """Return everything the browser needs to render the selected session."""
        return {
            "session": self.session,
            "topic_anchors": self.store.topic_anchors(self.learner, self.session),
            "sessions": self.store.sessions(self.learner),
            "conversation": self.store.conversation(
                self.learner, self.session, limit=None
            ),
            "exercise_status": self.store.exercise_statuses(self.learner, self.session),
            "learning": learning_view(
                self.store.learning_view(
                    self.store.learning_scope(self.learner, self.session)
                )
            ),
        }

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Read one HTTP request, validate it, and dispatch to the matching handler."""
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
            if len(request) > MAX_HEADER_BYTES:
                await self.respond(writer, 431, b"Request headers too large")
                return
            lines = request.decode("latin-1").split("\r\n")
            method, target, _version = lines[0].split(" ", 2)
            headers = {
                key.strip().lower(): value.strip()
                for line in lines[1:]
                if line and ":" in line
                for key, value in [line.split(":", 1)]
            }
            path = target.split("?", 1)[0]
            if not self.valid_host(headers.get("host", "")):
                await self.respond(writer, 400, b"Invalid host")
                return
            if method == "GET" and path in self.assets:
                content_type, asset = self.assets[path]
                await self.respond(
                    writer, 200, asset.read_bytes(), content_type=content_type
                )
                return
            if method == "GET" and path == "/api/bootstrap":
                async with self.lock:
                    await self.json_response(writer, 200, self.bootstrap())
                return
            if method == "POST" and path in {
                "/api/chat",
                "/api/session",
                "/api/exercise",
            }:
                if not self.valid_origin(headers.get("origin")):
                    await self.respond(writer, 403, b"Invalid origin")
                    return
                if (
                    headers.get("content-type", "").split(";", 1)[0]
                    != "application/json"
                ):
                    await self.respond(writer, 415, b"Expected application/json")
                    return
                length = int(headers.get("content-length", "0"))
                if not 0 <= length <= MAX_BODY_BYTES:
                    await self.respond(writer, 413, b"Request body too large")
                    return
                body = await reader.readexactly(length)
                payload = json.loads(body or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                if path == "/api/chat":
                    await self.chat(writer, payload)
                elif path == "/api/exercise":
                    await self.exercise(writer, payload)
                else:
                    await self.manage_session(writer, payload)
                return
            await self.respond(writer, 404, b"Not found")
        except (ValueError, json.JSONDecodeError, asyncio.IncompleteReadError):
            await self.respond(writer, 400, b"Invalid request")
        except TimeoutError:
            await self.respond(writer, 408, b"Request timeout")
        except Exception as exc:
            print(f"Web request failed: {type(exc).__name__}")
            await self.respond(writer, 500, b"Request failed")
        finally:
            writer.close()
            with suppress(ConnectionError, RuntimeError):
                await writer.wait_closed()

    def valid_host(self, host: str) -> bool:
        """Accept only this server's loopback host and port."""
        return host in {f"{HOST}:{self.port}", f"localhost:{self.port}"}

    def valid_origin(self, origin: str | None) -> bool:
        """Accept writes only from this server's loopback web origin."""
        if not origin:
            return False
        parsed = urlsplit(origin)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {HOST, "localhost"}
            and parsed.port == self.port
        )

    async def chat(self, writer: asyncio.StreamWriter, payload: dict) -> None:
        """Send a normal chat message to the tutor and return updated session data."""
        message = payload.get("message")
        if not isinstance(message, str):
            await self.respond(writer, 400, b"Message must be text")
            return
        try:
            async with self.lock:
                if payload.get("session", self.session) != self.session:
                    raise ValueError(
                        "The active session changed. Reopen your session and retry."
                    )
                reply = await self.tutor.respond(self.learner, self.session, message)
                result = {
                    "reply": reply.model_dump(mode="json"),
                    "topic_anchors": self.store.topic_anchors(
                        self.learner, self.session
                    ),
                    "sessions": self.store.sessions(self.learner),
                    "exercise_status": self.store.exercise_statuses(
                        self.learner, self.session
                    ),
                    "learning": learning_view(
                        self.store.learning_view(
                            self.store.learning_scope(self.learner, self.session)
                        )
                    ),
                }
            await self.json_response(writer, 200, result)
        except RateLimitError:
            await self.json_response(
                writer,
                429,
                {
                    "error": "Provider quota reached. Wait for it to reset; "
                    "this turn was not saved."
                },
            )
        except (APITimeoutError, TimeoutError):
            await self.json_response(
                writer,
                504,
                {
                    "error": "The model provider did not respond in time. "
                    "Your message was not saved; try again shortly."
                },
            )
        except ValueError as exc:
            await self.json_response(writer, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"Tutor turn failed: {type(exc).__name__}")
            await self.json_response(
                writer,
                500,
                {"error": "The turn failed and its learning changes were rolled back."},
            )

    async def exercise(self, writer: asyncio.StreamWriter, payload: dict) -> None:
        """Send an answer for a presented exercise to the tutor."""
        try:
            async with self.lock:
                if payload.get("session") != self.session:
                    raise ValueError(
                        "The active session changed. Reopen your session and retry."
                    )
                exercise_id, action = payload.get("exercise_id"), payload.get("action")
                if not isinstance(exercise_id, str) or action != "answer":
                    raise ValueError("Choose an exercise action")
                self.store.exercise_status(self.learner, self.session, exercise_id)
                result = await self._model_exercise_action(exercise_id, payload)
            await self.json_response(writer, 200, result)
        except RateLimitError:
            await self.json_response(
                writer,
                429,
                {"error": "Provider quota reached. This action was not saved."},
            )
        except (APITimeoutError, TimeoutError):
            await self.json_response(
                writer,
                504,
                {
                    "error": "The model provider did not respond in time. "
                    "This action was not saved; try again shortly."
                },
            )
        except (ValueError, PermissionError) as exc:
            await self.json_response(writer, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"Exercise action failed: {type(exc).__name__}")
            await self.json_response(
                writer,
                500,
                {"error": "The action failed and its changes were rolled back."},
            )

    async def _model_exercise_action(self, exercise_id: str, payload: dict) -> dict:
        """Call the tutor for an answer tied to a specific exercise."""
        message = payload.get("text", "")
        if not isinstance(message, str):
            raise ValueError("Answer must be text")
        reply = await self.tutor.respond(
            self.learner, self.session, message, exercise_id
        )
        return {
            "reply": reply.model_dump(mode="json"),
            "topic_anchors": self.store.topic_anchors(self.learner, self.session),
            "sessions": self.store.sessions(self.learner),
            "status": self.store.exercise_status(
                self.learner, self.session, exercise_id
            ),
            "exercise_status": self.store.exercise_statuses(self.learner, self.session),
            "learning": learning_view(
                self.store.learning_view(
                    self.store.learning_scope(self.learner, self.session)
                )
            ),
        }

    async def manage_session(self, writer: asyncio.StreamWriter, payload: dict) -> None:
        """Create, select, rename, or delete a session and return its full view."""
        try:
            async with self.lock:
                action = payload.get("action", "create")
                session = payload.get("session")
                if action == "create":
                    self.session = self.store.session(self.learner)
                elif action in {"select", "delete", "rename"}:
                    if not isinstance(session, str):
                        raise ValueError("Choose a session")
                    self.store.authorize(self.learner, session)
                    if action == "select":
                        self.session = session
                    elif action == "rename":
                        self.store.rename_session(
                            self.learner, session, payload.get("title", "")
                        )
                    else:
                        self.store.delete_session(self.learner, session)
                        if session == self.session:
                            remaining = self.store.sessions(self.learner)
                            self.session = (
                                remaining[0]["id"]
                                if remaining
                                else self.store.session(self.learner)
                            )
                else:
                    raise ValueError("Unknown session action")
                result = self.bootstrap()
            await self.json_response(writer, 200, result)
        except (ValueError, PermissionError) as exc:
            await self.json_response(writer, 400, {"error": str(exc)})

    async def json_response(
        self, writer: asyncio.StreamWriter, status: int, payload: dict
    ) -> None:
        """Serialize a payload as JSON and send it with the given HTTP status."""
        await self.respond(
            writer,
            status,
            json.dumps(payload, ensure_ascii=False).encode(),
            content_type="application/json; charset=utf-8",
        )

    async def respond(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        """Write one complete HTTP response with shared security headers."""
        reasons = {
            200: "OK",
            400: "Bad Request",
            403: "Forbidden",
            404: "Not Found",
            408: "Request Timeout",
            413: "Content Too Large",
            415: "Unsupported Media Type",
            429: "Too Many Requests",
            431: "Request Header Fields Too Large",
            500: "Internal Server Error",
            504: "Gateway Timeout",
        }
        headers = [
            f"HTTP/1.1 {status} {reasons[status]}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body)}",
            "Cache-Control: no-store",
            "X-Content-Type-Options: nosniff",
            "X-Frame-Options: DENY",
            "Referrer-Policy: no-referrer",
            "Content-Security-Policy: default-src 'self'; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; img-src 'self' data:",
            "Connection: close",
            "",
            "",
        ]
        writer.write("\r\n".join(headers).encode("ascii") + body)
        await writer.drain()


async def serve(settings: Settings, session: str | None, port: int) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Web port must be between 1024 and 65535")
    store = Store(settings.database)
    telemetry = Telemetry()
    tutor = Tutor(settings, store, telemetry)
    try:
        selected = session or store.latest_session(store.owner)
        session = store.session(store.owner, selected)
        application = WebApplication(store, tutor, session, port)
        server = await asyncio.start_server(
            application.handle, HOST, port, limit=MAX_HEADER_BYTES
        )
        print(f"Milai web · http://{HOST}:{port}")
        print("Local access only · Ctrl+C to stop")
        async with server:
            await server.serve_forever()
    finally:
        await tutor.close()
        store.close()
