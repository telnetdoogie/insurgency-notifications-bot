from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotifyAction:
    """Outbound chat notification. Voice/audio actions can sit beside this later."""

    message: str
    noisy: bool = False
