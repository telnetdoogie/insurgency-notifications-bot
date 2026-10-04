from __future__ import annotations

from pathlib import Path

from insurgency_bot.actions import NotifyAction
from insurgency_bot.config import load_known_users
from insurgency_bot.events import create_handlers
from insurgency_bot.runtime import run
from insurgency_bot.state.players import PlayerRoster
from insurgency_bot.state.server import ServerState

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class RecordingSink:
    def __init__(self) -> None:
        self.actions: list[NotifyAction] = []

    def send(self, action: object) -> None:
        if isinstance(action, NotifyAction):
            self.actions.append(action)

    @property
    def pairs(self) -> list[tuple[bool, str]]:
        return [(action.noisy, action.message) for action in self.actions]


def replay(path: str | Path, clock: FakeClock | None = None) -> tuple[RecordingSink, PlayerRoster, ServerState]:
    known = load_known_users(FIXTURES / "users.json")
    players = PlayerRoster(
        known=known,
        debounce_seconds=10.0,
        clock=clock or FakeClock(),
    )
    server = ServerState()
    sink = RecordingSink()
    run(
        Path(path).read_text(encoding="utf-8").splitlines(),
        create_handlers(),
        players,
        server,
        sink.send,
    )
    return sink, players, server
