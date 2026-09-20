"""Dependency-free local web interface for conversation and learning state."""

import asyncio
import json
from contextlib import suppress
from importlib.resources import files
from urllib.parse import urlsplit

from openai import RateLimitError

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
    def __init__(self, store: Store, tutor: Tutor, session: str, port: int):
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
        }

    def bootstrap(self) -> dict:
        return {
            "session": self.session,
            "conversation": self.store.conversation(
                self.learner, self.session, limit=50
            ),
            "learning": learning_view(self.store.learning_view(self.learner)),
        }

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
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
            if method == "POST" and path in {"/api/chat", "/api/session"}:
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
                if path == "/api/chat":
                    await self.chat(writer, payload)
                else:
                    await self.new_session(writer)
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
        return host in {f"{HOST}:{self.port}", f"localhost:{self.port}"}

    def valid_origin(self, origin: str | None) -> bool:
        if not origin:
            return False
        parsed = urlsplit(origin)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {HOST, "localhost"}
            and parsed.port == self.port
        )

    async def chat(self, writer: asyncio.StreamWriter, payload: dict) -> None:
        message = payload.get("message")
        if not isinstance(message, str):
            await self.respond(writer, 400, b"Message must be text")
            return
        try:
            async with self.lock:
                reply = await self.tutor.respond(self.learner, self.session, message)
                result = {
                    "reply": reply.model_dump(mode="json"),
                    "learning": learning_view(self.store.learning_view(self.learner)),
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
        except ValueError as exc:
            await self.json_response(writer, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"Tutor turn failed: {type(exc).__name__}")
            await self.json_response(
                writer,
                500,
                {"error": "The turn failed and its learning changes were rolled back."},
            )

    async def new_session(self, writer: asyncio.StreamWriter) -> None:
        async with self.lock:
            self.session = self.store.session(self.learner)
            result = self.bootstrap()
        await self.json_response(writer, 200, result)

    async def json_response(
        self, writer: asyncio.StreamWriter, status: int, payload: dict
    ) -> None:
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
        session = store.session(store.owner, session)
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
