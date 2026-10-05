"""Bounded public HTTP(S) fetching with validated destination addresses."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
import zlib
from threading import BoundedSemaphore, Event, Thread, Timer
from urllib.parse import SplitResult, urljoin, urlsplit

_TLS_CONTEXT = ssl.create_default_context()
_DNS_SLOT = BoundedSemaphore(1)


class FetchError(ValueError):
    """A safe error code; never contains URLs, headers or upstream content."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _check_address(value: str) -> str:
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise FetchError("blocked_url")
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            _check_address(str(address.ipv4_mapped))
        if address.sixtofour:
            _check_address(str(address.sixtofour))
        if address.teredo:
            for embedded in address.teredo:
                _check_address(str(embedded))
        if address in ipaddress.ip_network("64:ff9b::/96"):
            _check_address(str(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)))
    return str(address)


def validate_url(url: str) -> SplitResult:
    """Validate syntax without resolving DNS or disclosing the supplied URL."""
    try:
        if any(ord(char) <= 32 or ord(char) == 127 for char in url):
            raise FetchError("blocked_url")
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise FetchError("blocked_url")
        if parts.username is not None or parts.password is not None or parts.fragment:
            raise FetchError("blocked_url")
        if parts.port not in (None, 443 if parts.scheme == "https" else 80):
            raise FetchError("blocked_url")
        try:
            ipaddress.ip_address(parts.hostname)
        except ValueError:
            parts.hostname.encode("idna")
        else:
            _check_address(parts.hostname)
        return parts
    except (ValueError, UnicodeError):
        raise FetchError("blocked_url") from None


def _resolve_public(host: str, port: int, timeout: float = 3.0) -> str:
    # The OS resolver cannot be cancelled. Allow only one daemon lookup at a time,
    # so a stalled resolver neither holds refresh/shutdown nor accumulates threads.
    deadline = time.monotonic() + timeout
    if timeout <= 0 or not _DNS_SLOT.acquire(timeout=timeout):
        raise FetchError("timeout")
    done = Event()
    result: list = []

    def resolve() -> None:
        try:
            result.append(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except OSError:
            result.append(None)
        finally:
            _DNS_SLOT.release()
            done.set()

    Thread(target=resolve, daemon=True, name="source-dns").start()
    if not done.wait(max(0, deadline - time.monotonic())):
        raise FetchError("timeout")
    results = result[0] if result else None
    if not results:
        raise FetchError("dns_failed")
    addresses = [_check_address(str(result[4][0])) for result in results]
    return addresses[0]


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, secure: bool, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self.default_port = 443 if secure else 80
        self.address = address
        self.secure = secure

    def connect(self) -> None:
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        if self.secure:
            try:
                self.sock = _TLS_CONTEXT.wrap_socket(self.sock, server_hostname=self.host)
            except Exception:
                self.sock.close()
                raise


def _connection(
    host: str, port: int, address: str, secure: bool, timeout: float
) -> http.client.HTTPConnection:
    return _PinnedConnection(host, port, address, secure, timeout)


def fetch_bytes(url: str, *, max_bytes: int = 1_048_576, timeout: float = 10.0) -> bytes:
    """Fetch once, following at most three safe redirects; no ambient proxies or retries."""
    deadline = time.monotonic() + timeout
    for hop in range(4):
        parts = validate_url(url)
        secure = parts.scheme == "https"
        host = (parts.hostname or "").encode("idna").decode("ascii")
        port = 443 if secure else 80
        address = _resolve_public(host, port, max(0, deadline - time.monotonic()))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("timeout")
        connection = _connection(host, port, address, secure, min(3.0, remaining))
        timer = None
        response = None
        try:
            connection.connect()
            active_socket = connection.sock
            assert active_socket is not None
            active_socket.settimeout(min(3.0, max(0.01, deadline - time.monotonic())))

            def abort(active_socket=active_socket) -> None:
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = Timer(max(0.01, deadline - time.monotonic()), abort)
            timer.daemon = True
            timer.start()
            target = parts.path or "/"
            if parts.query:
                target += "?" + parts.query
            connection.request(
                "GET",
                target,
                headers={"User-Agent": "KindleFamilyDisplay/0.1", "Accept-Encoding": "identity"},
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location or hop == 3:
                    raise FetchError("redirect_blocked")
                redirected = urljoin(url, location)
                next_parts = validate_url(redirected)
                if secure and next_parts.scheme != "https":
                    raise FetchError("redirect_blocked")
                url = redirected
                continue
            if response.status != 200:
                raise FetchError("http_error")
            size_header = response.getheader("Content-Length")
            if size_header and int(size_header) > max_bytes:
                raise FetchError("body_too_large")
            encoding = response.getheader("Content-Encoding", "identity").lower()
            if encoding not in ("identity", "gzip"):
                raise FetchError("invalid_body")
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
            result = bytearray()
            transferred = 0
            while True:
                if time.monotonic() >= deadline:
                    raise FetchError("timeout")
                chunk = response.read1(8192)
                if not chunk:
                    break
                transferred += len(chunk)
                if transferred > max_bytes:
                    raise FetchError("body_too_large")
                decoded = (
                    decoder.decompress(chunk, max_bytes + 1 - len(result)) if decoder else chunk
                )
                result.extend(decoded)
                if len(result) > max_bytes:
                    raise FetchError("body_too_large")
            if decoder and (not decoder.eof or decoder.unused_data):
                raise FetchError("invalid_body")
            if size_header and transferred != int(size_header):
                raise FetchError("invalid_body")
            return bytes(result)
        except FetchError:
            raise
        except (OSError, http.client.HTTPException, ValueError, zlib.error) as error:
            code = (
                "timeout"
                if isinstance(error, TimeoutError) or time.monotonic() >= deadline
                else "http_error"
            )
            raise FetchError(code) from None
        finally:
            if timer:
                timer.cancel()
                timer.join()
            if response:
                response.close()
            connection.close()
    raise FetchError("redirect_blocked")
