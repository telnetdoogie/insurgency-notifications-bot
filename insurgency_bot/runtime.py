from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Sequence

from .actions import NotifyAction
from .events import EventHandler
from .normalize import normalize_line
from .state.players import PlayerRoster
from .state.server import ServerState

log = logging.getLogger(__name__)

Sink = Callable[[object], None]


def process_line(
    line: str,
    handlers: Sequence[EventHandler],
    players: PlayerRoster,
    server: ServerState,
    sink: Sink,
) -> None:
    line = normalize_line(line)
    if not line:
        return
    observe = getattr(players.clock, "observe", None)
    if callable(observe):
        observe(line)
    for handler in handlers:
        try:
            actions: Iterable[NotifyAction] = handler.handle(line, players, server) or []
        except Exception:
            log.exception("Event handler %s failed", type(handler).__name__)
            continue
        for action in actions:
            try:
                sink(action)
            except Exception:
                log.exception("Action sink failed")


def run(
    lines: Iterable[str],
    handlers: Sequence[EventHandler],
    players: PlayerRoster,
    server: ServerState,
    sink: Sink,
) -> None:
    for line in lines:
        process_line(line, handlers, players, server, sink)


def run_forever(
    source_factory: Callable[[], Iterable[str]],
    handlers: Sequence[EventHandler],
    players: PlayerRoster,
    server: ServerState,
    sink: Sink,
    reconnect_seconds: float = 2.0,
) -> None:
    while True:
        try:
            run(source_factory(), handlers, players, server, sink)
            log.info(
                "Docker log stream ended. Reconnecting in %s seconds...",
                reconnect_seconds,
            )
        except Exception as exc:
            log.warning(
                "Log stream error: %s. Reconnecting in %s seconds...",
                exc,
                reconnect_seconds,
            )
        players.reset_session()
        time.sleep(reconnect_seconds)
