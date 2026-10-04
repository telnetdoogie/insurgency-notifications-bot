from __future__ import annotations

import re
from collections.abc import Sequence

from ..actions import NotifyAction
from ..state.players import PlayerRoster
from ..state.server import MapChange, ServerState

TRAVEL_RE = re.compile(r"ProcessServerTravel:\s+([^?]+)\?[Ss]cenario=([^?\s]+)")
LIGHTING_RE = re.compile(r"\?[Ll]ighting=([^?\s]+)")
SCENARIO_RE = re.compile(r"^(.+)_([^_]+)_(Security|Insurgents)$")


def parse_travel(line: str) -> MapChange | None:
    match = TRAVEL_RE.search(line)
    if not match:
        return None

    internal_map = match.group(1)
    scenario = match.group(2)
    lighting_match = LIGHTING_RE.search(line)
    lighting = lighting_match.group(1) if lighting_match else "Unknown"

    scenario = scenario.removeprefix("Scenario_")
    parsed = SCENARIO_RE.match(scenario)
    if parsed:
        map_name, mode, side = parsed.group(1), parsed.group(2), parsed.group(3)
    else:
        map_name, mode, side = internal_map, "Unknown", "Unknown"

    return MapChange(
        map=map_name,
        mode=mode,
        side=side,
        lighting=lighting,
        internal_map=internal_map,
        scenario=scenario,
    )


class Handler:
    def handle(
        self,
        line: str,
        players: PlayerRoster,
        server: ServerState,
    ) -> Sequence[NotifyAction]:
        change = parse_travel(line)
        if change is None:
            return []
        server.apply_map_change(change)
        message = (
            f"🗺️ Map changing to: **{change.map}** — "
            f"{change.mode} / {change.side} / {change.lighting}"
        )
        return [NotifyAction(message, noisy=False)]
