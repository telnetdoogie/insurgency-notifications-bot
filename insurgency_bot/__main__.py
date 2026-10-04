from __future__ import annotations

import argparse
import logging
import signal
import sys

from .actions.discord_webhook import DiscordWebhookSink, StdoutSink
from .clock import UnrealLogClock
from .config import Config, load_known_users
from .events import create_handlers
from .runtime import run, run_forever
from .scanner import DockerLogSource, FileLogSource
from .state.players import PlayerRoster
from .state.server import ServerState


def _install_signals() -> None:
    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Watch Insurgency: Sandstorm container logs and send notifications."
    )
    parser.add_argument(
        "--file",
        help="Replay a log file instead of following docker.sock",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print notifications instead of posting to Discord",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _install_signals()

    cfg = Config.from_env()
    if not args.print_only:
        cfg.require_webhook()

    known = load_known_users(cfg.users_file)
    players = PlayerRoster(
        known=known,
        debounce_seconds=cfg.leave_debounce_seconds,
        clock=UnrealLogClock(),
    )
    server = ServerState()
    handlers = create_handlers()
    logging.getLogger(__name__).info("Loaded %s known users.", len(known))

    sink_obj = (
        StdoutSink()
        if args.print_only
        else DiscordWebhookSink(cfg.discord_webhook_url, cfg.discord_username)
    )

    def sink(action: object) -> None:
        sink_obj.send(action)

    if args.file:
        run(FileLogSource(args.file), handlers, players, server, sink)
        return 0

    def source_factory():
        return DockerLogSource(
            cfg.docker_socket,
            cfg.container_name,
            api_version=cfg.docker_api_version,
        )

    run_forever(
        source_factory,
        handlers,
        players,
        server,
        sink,
        reconnect_seconds=cfg.reconnect_seconds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
