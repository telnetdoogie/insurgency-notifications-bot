from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Sequence
from typing import Protocol

from ..actions import NotifyAction
from ..state.players import PlayerRoster
from ..state.server import ServerState


class EventHandler(Protocol):
    def handle(
        self,
        line: str,
        players: PlayerRoster,
        server: ServerState,
    ) -> Sequence[NotifyAction]:
        ...


def create_handlers() -> list[EventHandler]:
    """Load every events.* module that exports Handler.

    Drop a new module in this package with a Handler class to add an event.
    """
    handlers: list[EventHandler] = []
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name):
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        handler_cls = getattr(module, "Handler", None)
        if handler_cls is None:
            continue
        handlers.append(handler_cls())
    return handlers
