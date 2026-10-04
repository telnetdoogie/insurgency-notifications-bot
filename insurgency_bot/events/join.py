from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from ..actions import NotifyAction
from ..state.players import PlayerRoster
from ..state.server import ServerState

log = logging.getLogger(__name__)

LOGIN_RE = re.compile(
    r"Login request: \?Name=(.*) userId: SteamNWI:(\d+) platform:"
)
JOIN_RE = re.compile(r"LogNet: Join succeeded: (.+)$")


class Handler:
    def handle(
        self,
        line: str,
        players: PlayerRoster,
        server: ServerState,
    ) -> Sequence[NotifyAction]:
        login = LOGIN_RE.search(line)
        if login:
            name, steam_id = login.group(1), login.group(2)
            known = players.note_login(name, steam_id)
            if known:
                log.info("Known player login request: %s (%s)", name, steam_id)
            else:
                log.info("Other player login request: %s (%s)", name, steam_id)
            return []

        join = JOIN_RE.search(line)
        if not join:
            return []

        name = join.group(1).strip()
        result = players.complete_join(name)
        if result is None:
            return []

        if result.known is not None:
            tag = result.known.discord_tag
            if result.name_changed:
                message = f"🟢 {tag} joined the server as **{result.name}**"
            else:
                message = f"🟢 {tag} joined the server"
            return [NotifyAction(message, noisy=True)]

        return [NotifyAction(f"👤 '**{result.name}**' joined the server", noisy=False)]
