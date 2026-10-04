# Future: Discord voice announcer

Concept only. Not scheduled, not an implementation commitment.

The live bot is a stdlib log follower that POSTs Discord **webhooks**. That cannot join a voice channel. Voice is a second product: a real Discord bot that sits in one channel and plays short clips when game events fire.

## What we would build

The bot joins **one configured voice channel** and stays there. On selected events it plays audio, for example:

- “Doogie joined the server”
- later, stock callouts like “DOUBLE KILL!” if kill events become trustworthy

It does **not** listen to anyone, play music, or take voice commands. Self-deafen on join. Text webhooks stay as they are.

ElevenLabs (or a cached file) generates the sound. Discord voice is just the speaker.

## Why this is a different shape than v1

A webhook is one HTTP POST and no session.

Voice needs:

1. A Discord **application + bot token**, invited to the guild with Connect and Speak.
2. A persistent Gateway websocket (identify, heartbeat, resume).
3. A Voice State Update for the target channel.
4. A voice websocket plus **UDP** to Discord’s voice server, sending encrypted 20ms Opus frames while speaking.

The log follower can drop and reconnect in two seconds. A voice client that drops **leaves the channel**. Runtime has to keep two long-lived connections: Docker logs and Discord Gateway/voice. On container restart, rejoin the channel on purpose.

The image also stops being `python:3.12-slim` + stdlib. Typical stack:

- `discord.py[voice]` (async)
- PyNaCl / libsodium
- libopus
- ffmpeg in the image unless we only ever feed raw PCM/WAV

That is fine for a homelab sidecar. It is not a small patch on the current Dockerfile.

## Implementation thinking

Keep the current seams. Do not put Discord or ElevenLabs inside event parsers.

```text
log line
  → event module        (join / leave / later kill)
  → NotifyAction        (webhook, already exists)
  → SpeakAction         (new; clip id or text to speak)
       → Discord webhook sink     (unchanged)
       → Discord voice sink       (new; queue + play)
```

`SpeakAction` is the hole next to `NotifyAction`. Join can return both. Voice policy (which events speak, noisy vs silent) lives in the sink or a tiny policy module, not in `events/join.py`.

**Queue.** Two joins in one second must not overlap. Serialize playback. Drop or coalesce only with an explicit rule (probably: play everything, in order).

**Stay in the channel.** On ready / resume / voice disconnect, rejoin the configured channel. Do not follow users around.

**Self-deaf.** We do not need inbound audio.

**Same process is enough.** One container, log loop + asyncio Discord client. A second “voice sidecar” or Lavalink is overkill for two-second clips.

### Audio

Stock lines (`joined the server`, `DOUBLE KILL!`) should be **pre-rendered files**, not a live TTS round-trip. Live ElevenLabs is for names and one-off sentences, and it will always feel late for a kill callout.

Practical split:

| Kind | Source |
|---|---|
| Player names / “X joined” | ElevenLabs, cached by normalized name + line |
| Stock announcer stingers | Checked-in or volume-mounted clips |
| Discord wire format | 48 kHz stereo Opus (ffmpeg is the boring path) |

Cache aggressively. Do not hit ElevenLabs on every reconnect or every repeated join.

Secrets: bot token and ElevenLabs key from env, never git. Guild ID + voice channel ID are config.

### First slice (if we ever do this)

1. Bot token, join one channel, self-deaf, stay there.
2. On **known-player join** (the event we already trust), play a clip or a cached “{name} joined the server”.
3. Queue + restart rejoin.
4. Leave text webhooks alone.

That proves plumbing. It does not require kill tracking.

## DOUBLE KILL is not a voice problem

Voice for joins is product-ready. Announcer kills are blocked on **event quality**, the same reason kill tracking was removed from the log watcher.

`DoubleKillProtection` lines have names (or class names like Rifleman) and timestamps. They do not have team. Matching “both names are in the roster” is how teammates got announced as killers.

The logs *do* have team assignment (`joined team 1`, `Faction: Insurgents`). That belongs on `PlayerRoster` / `ServerState` first. Only then is a kill event honest enough to shout in voice.

Until that exists, either:

- do not play kill audio, or
- accept “any human kill” as flavor and say so explicitly.

Wrong text is easy to ignore. Wrong voice callouts are worse.

## Non-goals

- Listening to the channel / STT
- Music, playlists, Lavalink
- Following a user between channels
- Replacing the webhook
- Shipping voice in the current stdlib image
- Kill announcer before team-aware events

## Open choices (when this becomes real)

- discord.py vs Pycord (both need the same native stack)
- Live TTS vs names-as-clips + a stock “joined” tail
- Speak for known joins only, or unknown humans too
- Whether leave gets a line (text leave is already silent)
