from __future__ import annotations

import re
from collections.abc import Sequence

from ..actions import NotifyAction
from ..state.players import PlayerRoster
from ..state.server import ServerState

CLOSE_RE = re.compile(
    r"UChannel::Close:.*IsServer: YES.*UniqueId: SteamNWI:(\d+)"
)


class Handler:
    def handle(
        self,
        line: str,
        players: PlayerRoster,
        server: ServerState,
    ) -> Sequence[NotifyAction]:
        match = CLOSE_RE.search(line)
        if not match:
            return []

        result = players.disconnect(match.group(1))
        if result is None:
            return []

        tag = result.known.discord_tag
        if result.name_changed:
            message = f"🔴 {tag} (**{result.name}**) left the server"
        else:
            message = f"🔴 {tag} left the server"
        return [NotifyAction(message, noisy=False)]
