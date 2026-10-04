from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from insurgency_bot.scanner import iter_docker_log_frames, lines_from_chunks
from insurgency_bot.normalize import normalize_line


def frame(stream: int, payload: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


class NormalizeTests(unittest.TestCase):
    def test_strips_cr_and_compose_prefix(self) -> None:
        raw = "insurgency-sandstorm  | LogNet: Join succeeded: LouiSypher\r\n"
        self.assertEqual(normalize_line(raw), "LogNet: Join succeeded: LouiSypher")

    def test_leaves_raw_docker_log_lines_alone(self) -> None:
        line = "[2026.10.02-11.36.32:252][756]LogNet: Join succeeded: LouiSypher"
        self.assertEqual(normalize_line(line), line)


class DockerLogDecodeTests(unittest.TestCase):
    def test_demux_stdout_and_stderr_frames_into_lines(self) -> None:
        blob = (
            frame(1, b"first line\npartial")
            + frame(2, b" rest\n")
            + frame(1, b"last")
        )
        lines = list(lines_from_chunks(iter_docker_log_frames(io.BytesIO(blob), tty=False)))
        self.assertEqual(lines, ["first line", "partial rest", "last"])

    def test_tty_stream_is_raw_bytes(self) -> None:
        blob = b"aaa\nbbb\n"
        lines = list(lines_from_chunks(iter_docker_log_frames(io.BytesIO(blob), tty=True)))
        self.assertEqual(lines, ["aaa", "bbb"])


class DiscordWebhookTests(unittest.TestCase):
    def test_noisy_payload_has_no_suppress_flag(self) -> None:
        from insurgency_bot.actions import NotifyAction
        from insurgency_bot.actions.discord_webhook import DiscordWebhookSink

        captured: dict[str, object] = {}

        class FakeResponse:
            def read(self) -> bytes:
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args) -> None:
                return None

        def fake_urlopen(request, timeout=10.0):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            captured["user_agent"] = request.headers.get("User-agent") or request.get_header("User-agent")
            return FakeResponse()

        sink = DiscordWebhookSink("http://example.test/webhook", "Sandstorm")
        with patch("insurgency_bot.actions.discord_webhook.urllib.request.urlopen", fake_urlopen):
            sink.send(NotifyAction("🟢 hi", noisy=True))
            sink.send(NotifyAction("🗺️ map", noisy=False))

        self.assertEqual(captured["url"], "http://example.test/webhook")
        # last call is silent
        self.assertEqual(captured["body"]["flags"], 4096)
        self.assertEqual(captured["body"]["username"], "Sandstorm")
        self.assertEqual(captured["body"]["content"], "🗺️ map")
        ua = captured["user_agent"]
        self.assertIsInstance(ua, str)
        assert isinstance(ua, str)
        self.assertIn("DiscordBot", ua)
        self.assertNotIn("Python-urllib", ua)

    def test_noisy_then_inspect_first_payload(self) -> None:
        from insurgency_bot.actions import NotifyAction
        from insurgency_bot.actions.discord_webhook import DiscordWebhookSink

        payloads: list[dict] = []

        class FakeResponse:
            def read(self) -> bytes:
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args) -> None:
                return None

        def fake_urlopen(request, timeout=10.0):
            payloads.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        sink = DiscordWebhookSink("http://example.test/webhook", "Bot")
        with patch("insurgency_bot.actions.discord_webhook.urllib.request.urlopen", fake_urlopen):
            sink.send(NotifyAction("🟢 hi", noisy=True))

        self.assertNotIn("flags", payloads[0])
        self.assertEqual(payloads[0]["content"], "🟢 hi")


if __name__ == "__main__":
    unittest.main()
