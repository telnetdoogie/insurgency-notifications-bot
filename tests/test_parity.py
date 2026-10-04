from __future__ import annotations

import unittest

from insurgency_bot.events import create_handlers
from insurgency_bot.runtime import process_line, run
from insurgency_bot.state.players import PlayerRoster
from insurgency_bot.state.server import ServerState

from tests.support import FIXTURES, FakeClock, RecordingSink, replay


class ReplayTests(unittest.TestCase):
    def test_known_join_is_noisy_and_leave_is_silent(self) -> None:
        sink, players, _ = replay(FIXTURES / "known_join_leave.log")
        self.assertEqual(
            sink.pairs,
            [
                (True, "🟢 <@known-loui> joined the server"),
                (False, "🔴 <@known-loui> left the server"),
            ],
        )
        self.assertEqual(players.active, {})

    def test_join_request_and_team_lines_do_not_notify(self) -> None:
        sink, _, _ = replay(FIXTURES / "known_join_leave.log")
        self.assertEqual(len(sink.actions), 2)

    def test_unknown_join_is_silent_and_unknown_leave_is_omitted(self) -> None:
        sink, players, _ = replay(FIXTURES / "known_and_unknown.log")
        self.assertEqual(
            sink.pairs,
            [
                (True, "🟢 <@known-doogie> joined the server"),
                (False, "👤 '**freshlogic**' joined the server"),
                (False, "🔴 <@known-doogie> left the server"),
            ],
        )
        self.assertEqual(players.active, {})

    def test_name_mismatch_uses_session_name(self) -> None:
        sink, _, _ = replay(FIXTURES / "name_mismatch.log")
        self.assertEqual(
            sink.pairs,
            [
                (True, "🟢 <@known-doogie> joined the server as **DoogieAlt**"),
                (False, "🔴 <@known-doogie> (**DoogieAlt**) left the server"),
            ],
        )

    def test_map_changes_match_scenario_parsing_and_ignore_restart(self) -> None:
        sink, _, server = replay(FIXTURES / "map_changes.log")
        self.assertEqual(
            [message for _, message in sink.pairs],
            [
                "🗺️ Map changing to: **Gap** — Checkpoint / Insurgents / Unknown",
                "🗺️ Map changing to: **Crossing** — Checkpoint / Security / Night",
                "🗺️ Map changing to: **Outskirts** — Checkpoint / Insurgents / Day",
                "🗺️ Map changing to: **Forest** — Checkpoint / Security / Day",
                "🗺️ Map changing to: **Hideout** — Checkpoint / Insurgents / Day",
            ],
        )
        self.assertIsNotNone(server.current)
        assert server.current is not None
        self.assertEqual(server.current.map, "Hideout")
        self.assertEqual(server.current.internal_map, "Town")

    def test_compose_prefix_is_stripped(self) -> None:
        sink, _, _ = replay(FIXTURES / "compose_prefix.log")
        self.assertEqual(sink.pairs, [(True, "🟢 <@known-doogie> joined the server")])

    def test_kill_lines_are_ignored(self) -> None:
        sink, _, _ = replay(FIXTURES / "kills_ignored.log")
        self.assertEqual(sink.pairs, [])

    def test_duplicate_join_does_not_renotify(self) -> None:
        lines = [
            "LogNet: Login request: ?Name=LouiSypher userId: SteamNWI:76561198000000002 platform: SteamNWI",
            "LogNet: Join succeeded: LouiSypher",
            "LogNet: Login request: ?Name=LouiSypher userId: SteamNWI:76561198000000002 platform: SteamNWI",
            "LogNet: Join succeeded: LouiSypher",
        ]
        sink, _, _ = replay_lines(lines)
        self.assertEqual(sink.pairs, [(True, "🟢 <@known-loui> joined the server")])

    def test_leave_debounce_skips_flapping_known_player(self) -> None:
        clock = FakeClock()
        sink = RecordingSink()
        players = PlayerRoster(
            known=replay_roster().known,
            debounce_seconds=10.0,
            clock=clock,
        )
        handlers = create_handlers()
        join_lines = [
            "LogNet: Login request: ?Name=LouiSypher userId: SteamNWI:76561198000000002 platform: SteamNWI",
            "LogNet: Join succeeded: LouiSypher",
        ]
        run(join_lines, handlers, players, ServerState(), sink.send)
        close = (
            "LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] "
            "ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 203.0.113.10:1, "
            "Name: IpConnection_1, Driver: GameNetDriver IpNetDriver_1, IsServer: YES, "
            "PC: INSPlayerController_1, Owner: INSPlayerController_1, "
            "UniqueId: SteamNWI:76561198000000002"
        )
        process_line(close, handlers, players, ServerState(), sink.send)
        clock.advance(9.0)
        process_line(close, handlers, players, ServerState(), sink.send)
        clock.advance(2.0)
        process_line(close, handlers, players, ServerState(), sink.send)
        leaves = [message for noisy, message in sink.pairs if not noisy]
        self.assertEqual(
            leaves,
            [
                "🔴 <@known-loui> left the server",
                "🔴 <@known-loui> left the server",
            ],
        )

    def test_known_leave_without_join_still_notifies(self) -> None:
        close = (
            "LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] "
            "ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 203.0.113.10:1, "
            "Name: IpConnection_1, Driver: GameNetDriver IpNetDriver_1, IsServer: YES, "
            "PC: INSPlayerController_1, Owner: INSPlayerController_1, "
            "UniqueId: SteamNWI:76561198000000001"
        )
        sink, _, _ = replay_lines([close])
        self.assertEqual(sink.pairs, [(False, "🔴 <@known-doogie> left the server")])

    def test_reset_session_clears_roster_but_keeps_debounce(self) -> None:
        clock = FakeClock()
        players = replay_roster(clock)
        handlers = create_handlers()
        sink = RecordingSink()
        run(
            [
                "LogNet: Login request: ?Name=LouiSypher userId: SteamNWI:76561198000000002 platform: SteamNWI",
                "LogNet: Join succeeded: LouiSypher",
            ],
            handlers,
            players,
            ServerState(),
            sink.send,
        )
        players.reset_session()
        self.assertEqual(players.active, {})
        self.assertEqual(players.pending, {})
        close = (
            "LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] "
            "ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 203.0.113.10:1, "
            "Name: IpConnection_1, Driver: GameNetDriver IpNetDriver_1, IsServer: YES, "
            "PC: INSPlayerController_1, Owner: INSPlayerController_1, "
            "UniqueId: SteamNWI:76561198000000002"
        )
        process_line(close, handlers, players, ServerState(), sink.send)
        clock.advance(1.0)
        process_line(close, handlers, players, ServerState(), sink.send)
        self.assertEqual(
            [message for noisy, message in sink.pairs if not noisy],
            ["🔴 <@known-loui> left the server"],
        )

    def test_log_timestamps_drive_leave_debounce(self) -> None:
        from insurgency_bot.clock import UnrealLogClock

        lines = [
            "[2026.10.02-14.01.08:163][390]LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 192.0.2.1:1, Name: IpConnection_1, Driver: GameNetDriver IpNetDriver_1, IsServer: YES, PC: INSPlayerController_1, Owner: INSPlayerController_1, UniqueId: SteamNWI:76561198000000001",
            "[2026.10.02-14.01.12:163][390]LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 192.0.2.1:1, Name: IpConnection_1, Driver: GameNetDriver IpNetDriver_1, IsServer: YES, PC: INSPlayerController_1, Owner: INSPlayerController_1, UniqueId: SteamNWI:76561198000000001",
            "[2026.10.02-15.16.15:951][557]LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 192.0.2.1:1, Name: IpConnection_1, Driver: GameNetDriver IpNetDriver_1, IsServer: YES, PC: INSPlayerController_1, Owner: INSPlayerController_1, UniqueId: SteamNWI:76561198000000001",
        ]
        players = PlayerRoster(
            known=replay_roster().known,
            debounce_seconds=10.0,
            clock=UnrealLogClock(),
        )
        sink = RecordingSink()
        run(lines, create_handlers(), players, ServerState(), sink.send)
        self.assertEqual(
            sink.pairs,
            [
                (False, "🔴 <@known-doogie> left the server"),
                (False, "🔴 <@known-doogie> left the server"),
            ],
        )

    def test_autodiscovery_loads_join_leave_and_map(self) -> None:
        names = sorted(type(handler).__module__.split(".")[-1] for handler in create_handlers())
        self.assertEqual(names, ["join", "leave", "map_change"])


def replay_roster(clock: FakeClock | None = None) -> PlayerRoster:
    from insurgency_bot.config import load_known_users

    return PlayerRoster(
        known=load_known_users(FIXTURES / "users.json"),
        debounce_seconds=10.0,
        clock=clock or FakeClock(),
    )


def replay_lines(lines: list[str], clock: FakeClock | None = None) -> tuple[RecordingSink, PlayerRoster, ServerState]:
    players = replay_roster(clock)
    server = ServerState()
    sink = RecordingSink()
    run(lines, create_handlers(), players, server, sink.send)
    return sink, players, server


if __name__ == "__main__":
    unittest.main()
