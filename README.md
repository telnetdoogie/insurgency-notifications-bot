# insurgency-notifications-bot

Tiny Python watcher for an **Insurgency: Sandstorm** dedicated server running in Docker. It follows that container's logs through `/var/run/docker.sock` and sends Discord webhook notifications.

## What it notifies today

- Known player join — noisy Discord notification
- Unknown human join — silent
- Known or unknown player leave — silent, with a 10s flap debounce
- Map / scenario change — silent
- Steam name ≠ configured name is called out on join/leave

Kill tracking is **not** included. `DoubleKillProtection` log lines have names and timestamps, not teams, so they mis-attribute teammate kills.

## Run with Docker

1. Copy `.env.example` to `.env` and set `DISCORD_WEBHOOK_URL`.
2. Fill in `users.json` (Steam ID, in-game name, Discord mention).
3. Start next to the Sandstorm container:

```bash
docker compose up -d --build
```

The watcher mounts the host Docker socket and follows `CONTAINER_NAME` (default `insurgency-sandstorm`).

### Environment

- `DISCORD_WEBHOOK_URL` — required Discord webhook
- `DISCORD_USERNAME` — webhook display name (default `Sandstorm`)
- `CONTAINER_NAME` — container whose logs to follow (default `insurgency-sandstorm`)
- `DOCKER_SOCKET` — Docker Engine socket (default `/var/run/docker.sock`)
- `USERS_FILE` — known-player list (default `/config/users.json`)
- `RECONNECT_SECONDS` — wait after the log stream drops (default `2`)
- `LEAVE_DEBOUNCE_SECONDS` — ignore repeat leaves for the same Steam ID (default `10`)

`docker.sock` is powerful (it is effectively host root). This is meant as a homelab sidecar, not a locked-down multi-tenant service.

## Local replay

Useful against a saved log, no Discord:

```bash
PYTHONPATH=. python -m insurgency_bot --print-only --file /path/to/server.log
```

## Layout

```text
insurgency_bot/
  __main__.py          runtime CLI
  scanner.py           docker.sock (and file) log source
  runtime.py           line loop + reconnect
  state/players.py     roster, pending joins, leave debounce
  state/server.py      current map
  events/join.py       login + join
  events/leave.py      disconnect
  events/map_change.py ProcessServerTravel
  actions/             Discord webhook (voice/audio can sit beside this later)
```

### Adding an event

Create `insurgency_bot/events/your_event.py` with a `Handler` class:

```python
class Handler:
    def handle(self, line, players, server):
        # return a list of NotifyAction(message, noisy=False)
        return []
```

Modules in that folder are auto-loaded. Keep parsing in the event; keep who-is-online / what-map-is-up in `players` / `server`; do not post to Discord from the event.

## Tests

Fixtures are redacted slices of real dedicated-server logs (Steam IDs and IPs replaced).

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```
