from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .state.players import KnownUser


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def default_users_file() -> str:
    for path in ("/config/users.json", "users.json"):
        if os.path.isfile(path):
            return path
    return "users.json"


@dataclass(frozen=True)
class Config:
    container_name: str
    docker_socket: str
    docker_api_version: str
    discord_webhook_url: str
    discord_username: str
    users_file: str
    reconnect_seconds: float
    leave_debounce_seconds: float

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            container_name=_env("CONTAINER_NAME", "insurgency-sandstorm"),
            docker_socket=_env("DOCKER_SOCKET", "/var/run/docker.sock"),
            docker_api_version=_env("DOCKER_API_VERSION", "1.43"),
            discord_webhook_url=_env("DISCORD_WEBHOOK_URL", ""),
            discord_username=_env("DISCORD_USERNAME", "Sandstorm"),
            users_file=_env("USERS_FILE", default_users_file()),
            reconnect_seconds=float(_env("RECONNECT_SECONDS", "2")),
            leave_debounce_seconds=float(_env("LEAVE_DEBOUNCE_SECONDS", "10")),
        )

    def require_webhook(self) -> None:
        if not self.discord_webhook_url:
            raise SystemExit("DISCORD_WEBHOOK_URL is required unless --print-only is set")


def load_known_users(path: str | os.PathLike[str]) -> dict[str, KnownUser]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    users: dict[str, KnownUser] = {}
    for raw in data.get("users", []):
        steam_id = str(raw.get("steam_id", "")).strip()
        if not steam_id:
            continue
        users[steam_id] = KnownUser(
            steam_id=steam_id,
            player_name=str(raw.get("player_name", "")),
            discord_tag=str(raw.get("discord_tag", "")),
        )
    return users
