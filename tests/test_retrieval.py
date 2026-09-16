import socket

import pytest

from milai.retrieval import MAX_BYTES, fetch, public_address


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com",
        "https://user:pass@example.com",
        "https://127.0.0.1",
        "https://[::1]",
        "https://169.254.169.254/metadata",
        "https://example.com:8443",
        "https://example.com/#fragment",
    ],
)
def test_unsafe_urls_fail_closed(url):
    assert fetch(url)["status"] == "unavailable"


def test_mixed_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (2, 1, 6, "", ("93.184.215.14", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(ValueError, match="public"):
        public_address("example.com")


@pytest.mark.parametrize(
    "status,mime,body,expected",
    [
        (
            200,
            "text/html",
            b"<title>A</title><script>secret</script><p>Readable</p>",
            "available",
        ),
        (302, "text/html", b"redirect", "unavailable"),
        (200, "application/pdf", b"pdf", "unavailable"),
        (200, "text/plain", b"x" * (MAX_BYTES + 1), "unavailable"),
    ],
)
def test_bounded_fetch_and_no_redirects(monkeypatch, status, mime, body, expected):
    addresses = []

    class Connection:
        def __init__(self, host, address):
            self.status = status
            self.sock = None
            self.remaining = body
            addresses.append(address)

        def request(self, method, path, headers):
            assert "Authorization" not in headers

        def getresponse(self):
            return self

        def getheader(self, name, default=None):
            return mime if name == "Content-Type" else default

        def read1(self, limit):
            chunk, self.remaining = self.remaining[:limit], self.remaining[limit:]
            return chunk

        def close(self):
            pass

    monkeypatch.setattr("milai.retrieval.public_address", lambda _: "93.184.215.14")
    monkeypatch.setattr("milai.retrieval.PinnedHTTPS", Connection)
    result = fetch("https://example.com")
    assert result["status"] == expected
    assert addresses == ["93.184.215.14"]
    if expected == "available":
        assert "Readable" in result["text"]
        assert "secret" not in result["text"]
        assert result["url"] == "https://example.com"
