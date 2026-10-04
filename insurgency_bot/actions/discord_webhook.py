from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from . import NotifyAction

log = logging.getLogger(__name__)

SILENT_FLAG = 4096  # SUPPRESS_NOTIFICATIONS


class DiscordWebhookSink:
    def __init__(self, url: str, username: str, timeout: float = 10.0) -> None:
        self.url = url
        self.username = username
        self.timeout = timeout

    def send(self, action: object) -> None:
        if not isinstance(action, NotifyAction):
            return
        log.info("%s", action.message)
        payload: dict[str, object] = {
            "username": self.username,
            "content": action.message,
        }
        if not action.noisy:
            payload["flags"] = SILENT_FLAG
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            log.warning("Discord webhook failed: %s", exc)


class StdoutSink:
    def send(self, action: object) -> None:
        if not isinstance(action, NotifyAction):
            return
        kind = "notify" if action.noisy else "silent"
        print(f"{kind}: {action.message}", flush=True)
