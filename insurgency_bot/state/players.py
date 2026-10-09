from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

Clock = Callable[[], float]


@dataclass(frozen=True)
class KnownUser:
    steam_id: str
    player_name: str
    discord_tag: str


@dataclass(frozen=True)
class JoinResult:
    steam_id: str
    name: str
    known: KnownUser | None
    name_changed: bool


@dataclass(frozen=True)
class LeaveResult:
    steam_id: str
    name: str
    known: KnownUser | None
    name_changed: bool


@dataclass
class PlayerRoster:
    known: dict[str, KnownUser]
    debounce_seconds: float = 10.0
    clock: Clock = time.monotonic
    pending: dict[str, str] = field(default_factory=dict)  # session name -> steam_id
    active: dict[str, str] = field(default_factory=dict)  # steam_id -> session name
    last_leave: dict[str, float] = field(default_factory=dict)

    def note_login(self, name: str, steam_id: str) -> KnownUser | None:
        self.pending[name] = steam_id
        return self.known.get(steam_id)

    def complete_join(self, name: str) -> JoinResult | None:
        steam_id = self.pending.pop(name, None)
        if not steam_id:
            return None
        if steam_id in self.active:
            return None
        self.active[steam_id] = name
        known = self.known.get(steam_id)
        name_changed = bool(known and name != known.player_name)
        return JoinResult(
            steam_id=steam_id,
            name=name,
            known=known,
            name_changed=name_changed,
        )

    def disconnect(self, steam_id: str) -> LeaveResult | None:
        name = self.active.pop(steam_id, None)
        known = self.known.get(steam_id)
        # Known players still resolve through users.json. Unknown players need
        # the session name from a join we actually saw.
        session_name = name or (known.player_name if known else None)
        if session_name is None:
            return None
        now = self.clock()
        last = self.last_leave.get(steam_id)
        if last is not None and (now - last) < self.debounce_seconds:
            return None
        self.last_leave[steam_id] = now
        return LeaveResult(
            steam_id=steam_id,
            name=session_name,
            known=known,
            name_changed=bool(known and session_name != known.player_name),
        )

    def reset_session(self) -> None:
        """Forget who is in-server after the log stream drops. Keep leave debounce."""
        self.pending.clear()
        self.active.clear()

    def steam_id_by_name(self, name: str) -> str | None:
        for steam_id, session_name in self.active.items():
            if session_name == name:
                return steam_id
        return None
