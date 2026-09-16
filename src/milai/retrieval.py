"""Topic-neutral HTTPS retrieval with pinned public DNS and bounded responses."""

import asyncio
import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from milai.store import now

MAX_BYTES = 256_000
MAX_TEXT = 6000


def public_address(host: str) -> str:
    addresses = {
        str(item[4][0])
        for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    }
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Source must resolve only to public internet addresses")
    return sorted(addresses)[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str):
        self.tls_context = ssl.create_default_context()
        super().__init__(host, timeout=10, context=self.tls_context)
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self.tls_context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fetch(url: str) -> dict:
    base = {"url": url, "retrieved_at": now()}
    connection = None
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or parts.fragment
            or len(url) > 2000
            or any(ord(c) < 33 for c in url)
        ):
            raise ValueError(
                "Use a public HTTPS URL on port 443 without credentials or fragment"
            )
        host = parts.hostname.encode("idna").decode("ascii")
        address = public_address(host)
        connection = PinnedHTTPS(host, address)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        connection.request(
            "GET",
            path,
            headers={
                "User-Agent": "MilaiTutor/0.2",
                "Accept": "text/html,text/plain",
                "Accept-Encoding": "identity",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            return {
                **base,
                "status": "unavailable",
                "reason": f"HTTP {response.status}; redirects are not followed",
            }
        content_type = response.getheader("Content-Type", "").split(";")[0].lower()
        if content_type not in ("text/plain", "text/html"):
            raise ValueError(
                "Only public text and HTML are supported; paste an excerpt instead"
            )
        if response.getheader("Content-Encoding", "identity") != "identity":
            raise ValueError("Compressed responses are unsupported")
        deadline = time.monotonic() + 12
        chunks = []
        size = 0
        while size <= MAX_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Source read deadline exceeded")
            if connection.sock is not None:
                connection.sock.settimeout(min(10, remaining))
            chunk = response.read1(min(16384, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_BYTES:
            raise ValueError("Source exceeds retrieval byte limit")
        if content_type == "text/html":
            soup = BeautifulSoup(raw, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else host
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
        else:
            title, text = host, raw.decode("utf-8", errors="replace")
        if not text.strip():
            raise ValueError("Source contained no extractable text")
        return {
            **base,
            "status": "available",
            "title": title[:300],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "text": text[:MAX_TEXT],
            "truncated": len(text) > MAX_TEXT,
        }
    except (ValueError, OSError, http.client.HTTPException):
        # URL remains inspectable; don't echo response bodies or arbitrary exceptions.
        return {
            **base,
            "status": "unavailable",
            "reason": (
                "Blocked, unreachable, oversized or unsupported source; "
                "ask for a public text URL or pasted excerpt"
            ),
        }
    finally:
        if connection:
            connection.close()


async def retrieve(url: str) -> dict:
    return await asyncio.wait_for(asyncio.to_thread(fetch, url), timeout=20)
