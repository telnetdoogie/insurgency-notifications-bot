from __future__ import annotations

import http.client
import json
import logging
import socket
from collections.abc import Iterator
from urllib.parse import quote

log = logging.getLogger(__name__)


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float | None = None) -> None:
        super().__init__("docker", timeout=timeout)
        self._unix_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            sock.settimeout(self.timeout)
        sock.connect(self._unix_path)
        self.sock = sock


def _read_exact(fp, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        piece = fp.read(size - len(chunks))
        if not piece:
            break
        chunks.extend(piece)
    return bytes(chunks)


def iter_docker_log_frames(fp, tty: bool) -> Iterator[bytes]:
    """Yield payload bytes from a Docker logs stream."""
    if tty:
        while True:
            chunk = fp.read(4096)
            if not chunk:
                return
            yield chunk
        return

    while True:
        header = _read_exact(fp, 8)
        if not header:
            return
        if len(header) < 8:
            return
        size = int.from_bytes(header[4:8], "big")
        payload = _read_exact(fp, size) if size else b""
        if size and len(payload) < size:
            return
        if payload:
            yield payload


def lines_from_chunks(chunks: Iterator[bytes]) -> Iterator[str]:
    buf = b""
    for chunk in chunks:
        buf += chunk
        while True:
            index = buf.find(b"\n")
            if index < 0:
                break
            raw, buf = buf[:index], buf[index + 1 :]
            yield raw.decode("utf-8", "replace")
    if buf:
        yield buf.decode("utf-8", "replace")


class FileLogSource:
    def __init__(self, path: str) -> None:
        self.path = path

    def __iter__(self) -> Iterator[str]:
        with open(self.path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line


class DockerLogSource:
    def __init__(
        self,
        socket_path: str,
        container: str,
        api_version: str = "1.43",
        tail: int = 0,
        follow: bool = True,
        inspect_timeout: float = 10.0,
    ) -> None:
        self.socket_path = socket_path
        self.container = container
        self.api_version = api_version
        self.tail = tail
        self.follow = follow
        self.inspect_timeout = inspect_timeout

    def _path(self, suffix: str) -> str:
        name = quote(self.container, safe="")
        return f"/v{self.api_version}/containers/{name}/{suffix}"

    def _inspect_tty(self) -> bool:
        conn = UnixHTTPConnection(self.socket_path, timeout=self.inspect_timeout)
        try:
            conn.request("GET", self._path("json"))
            response = conn.getresponse()
            body = response.read()
            if response.status == 404:
                raise FileNotFoundError(f"container not found: {self.container}")
            if response.status >= 400:
                raise RuntimeError(
                    f"docker inspect failed: HTTP {response.status} {body[:200]!r}"
                )
            info = json.loads(body.decode("utf-8"))
            return bool(info.get("Config", {}).get("Tty"))
        finally:
            conn.close()

    def __iter__(self) -> Iterator[str]:
        tty = self._inspect_tty()
        params = (
            f"stdout=1&stderr=1&timestamps=0"
            f"&follow={1 if self.follow else 0}&tail={self.tail}"
        )
        conn = UnixHTTPConnection(self.socket_path, timeout=None)
        try:
            conn.request("GET", f"{self._path('logs')}?{params}")
            response = conn.getresponse()
            if response.status == 404:
                raise FileNotFoundError(f"container not found: {self.container}")
            if response.status >= 400:
                body = response.read(200)
                raise RuntimeError(
                    f"docker logs failed: HTTP {response.status} {body!r}"
                )
            log.info("Watching Docker container: %s", self.container)
            yield from lines_from_chunks(iter_docker_log_frames(response, tty))
        finally:
            conn.close()
