from __future__ import annotations

import re
import time
from datetime import datetime, timezone

# [2026.10.02-23.24.56:692]
_UNREAL_TS = re.compile(r"\[(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2}):")


class UnrealLogClock:
    """Use timestamps from Unreal log lines so file replay and live follow agree."""

    def __init__(self) -> None:
        self._now = time.time()

    def observe(self, line: str) -> None:
        match = _UNREAL_TS.search(line)
        if not match:
            return
        year, month, day, hour, minute, second = (int(part) for part in match.groups())
        self._now = datetime(
            year, month, day, hour, minute, second, tzinfo=timezone.utc
        ).timestamp()

    def __call__(self) -> float:
        return self._now
