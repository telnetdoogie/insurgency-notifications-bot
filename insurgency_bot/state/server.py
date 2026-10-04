from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MapChange:
    map: str
    mode: str
    side: str
    lighting: str
    internal_map: str
    scenario: str


@dataclass
class ServerState:
    current: MapChange | None = field(default=None)

    def apply_map_change(self, change: MapChange) -> MapChange:
        self.current = change
        return change
