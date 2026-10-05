import gzip
import socket
from io import BytesIO

import pytest

from app.collectors import http


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:password@example.org/calendar",
        "https://example.org:8443/feed",
        "http://127.0.0.1/feed",
        "https://[::1]/feed",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_rejects_unsafe_urls_and_addresses(url):
    with pytest.raises(http.FetchError):
        http.fetch_bytes(url)


def test_rejects_dns_with_any_nonpublic_address(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
        ],
    )
    with pytest.raises(http.FetchError, match="blocked_url"):
        http.fetch_bytes("https://public.example/feed")


class FakeSocket:
    def settimeout(self, timeout):
        pass

    def shutdown(self, how):
        pass


class Response:
    def __init__(self, body=b"feed", status=200, headers=None):
        self.body = BytesIO(body)
        self.status = status
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, size):
        return self.body.read(size)

    def close(self):
        pass


class Connection:
    def __init__(self, response):
        self.response = response
        self.sock = FakeSocket()

    def connect(self):
        pass

    def request(self, *args, **kwargs):
        pass

    def getresponse(self):
        return self.response

    def close(self):
        pass


def setup_http(monkeypatch, responses):
    hosts = []
    monkeypatch.setattr(http, "_resolve_public", lambda host, port, timeout: "93.184.216.34")

    def connect(host, port, address, secure, timeout):
        hosts.append((host, address, secure))
        return Connection(responses.pop(0))

    monkeypatch.setattr(http, "_connection", connect)
    return hosts


def test_connects_to_validated_address_and_preserves_original_host(monkeypatch):
    hosts = setup_http(monkeypatch, [Response()])
    assert http.fetch_bytes("https://feed.example/path?private=token") == b"feed"
    assert hosts == [("feed.example", "93.184.216.34", True)]


def test_pinned_connection_does_not_resolve_hostname_again(monkeypatch):
    addresses = []

    class DummySocket:
        def setsockopt(self, *args):
            pass

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda address, *a, **k: addresses.append(address) or DummySocket(),
    )
    connection = http._connection("feed.example", 80, "93.184.216.34", False, 3)
    connection.connect()
    assert addresses == [("93.184.216.34", 80)]


def test_redirects_are_revalidated_and_cannot_downgrade(monkeypatch):
    setup_http(
        monkeypatch, [Response(status=302, headers={"Location": "http://feed.example/feed"})]
    )
    with pytest.raises(http.FetchError, match="redirect_blocked"):
        http.fetch_bytes("https://feed.example/feed")


def test_redirect_to_private_address_is_rejected(monkeypatch):
    setup_http(
        monkeypatch, [Response(status=302, headers={"Location": "https://127.0.0.1/private"})]
    )
    with pytest.raises(http.FetchError, match="blocked_url"):
        http.fetch_bytes("https://feed.example/feed")


def test_bounds_plain_and_decompressed_bytes(monkeypatch):
    setup_http(monkeypatch, [Response(b"x" * 100)])
    with pytest.raises(http.FetchError, match="body_too_large"):
        http.fetch_bytes("https://feed.example/feed", max_bytes=20)
    setup_http(
        monkeypatch, [Response(gzip.compress(b"x" * 1000), headers={"Content-Encoding": "gzip"})]
    )
    with pytest.raises(http.FetchError, match="body_too_large"):
        http.fetch_bytes("https://feed.example/feed", max_bytes=100)


def test_gzip_is_decoded_and_truncated_gzip_rejected(monkeypatch):
    setup_http(
        monkeypatch, [Response(gzip.compress(b"calendar"), headers={"Content-Encoding": "gzip"})]
    )
    assert http.fetch_bytes("https://feed.example/feed") == b"calendar"
    setup_http(
        monkeypatch,
        [Response(gzip.compress(b"calendar")[:-5], headers={"Content-Encoding": "gzip"})],
    )
    with pytest.raises(http.FetchError, match="invalid_body"):
        http.fetch_bytes("https://feed.example/feed")


def test_error_message_never_contains_private_url(monkeypatch):
    setup_http(monkeypatch, [Response(status=500)])
    with pytest.raises(http.FetchError) as error:
        http.fetch_bytes("https://feed.example/private?token=secret")
    assert str(error.value) == "http_error"


def test_https_uses_standard_host_header_without_default_port():
    connection = http._connection("feed.example", 443, "93.184.216.34", True, 3)
    connection.putrequest("GET", "/calendar")
    headers = b"\r\n".join(connection._buffer)
    assert b"Host: feed.example\r\n" in headers + b"\r\n"
    assert b"Host: feed.example:443" not in headers


def test_dns_deadline_and_stalled_resolver_do_not_accumulate_workers(monkeypatch):
    import threading
    import time

    blocked = threading.Event()
    calls = []

    def resolver(*args, **kwargs):
        calls.append(1)
        blocked.wait(2)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    started = time.monotonic()
    try:
        for _ in range(2):
            with pytest.raises(http.FetchError, match="timeout"):
                http.fetch_bytes("https://feed.example/feed", timeout=0.03)
        assert time.monotonic() - started < 0.5
        assert len(calls) == 1
    finally:
        blocked.set()


def test_rejects_truncated_content_length(monkeypatch):
    setup_http(monkeypatch, [Response(b"feed", headers={"Content-Length": "10"})])
    with pytest.raises(http.FetchError, match="invalid_body"):
        http.fetch_bytes("https://feed.example/feed")
