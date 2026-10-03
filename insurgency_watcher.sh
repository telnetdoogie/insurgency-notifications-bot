#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "$0")"

CONTAINER="insurgency-sandstorm"
USERS_FILE="$SCRIPT_DIR/users.json"
DISCORD_SCRIPT="$SCRIPT_DIR/sendToDiscord.sh"

PID_FILE="/tmp/sandstorm-watcher.pid"
WATCHER_LOG="/tmp/sandstorm-watcher.log"

declare -A PLAYER_NAMES
declare -A DISCORD_TAGS
declare -A PENDING_USERS
declare -A PENDING_KILL_VICTIMS
declare -A ACTIVE_USERS
declare -A LAST_LEAVE



# ----------------------------------------------------------------------
# Process management
# ----------------------------------------------------------------------

is_running() {
    [[ -f "$PID_FILE" ]] || return 1

    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null)"

    [[ -n "$pid" ]] || return 1
    kill -0 "$pid" 2>/dev/null
}


start_watcher() {
    if is_running; then
        echo "Sandstorm watcher is already running (PID $(cat "$PID_FILE"))."
        exit 1
    fi

    # Remove stale PID file if present.
    rm -f "$PID_FILE"

    echo "Starting Sandstorm watcher..."

    #
    # setsid gives the watcher its own process group/session.
    # That lets -stop cleanly kill the watcher AND its docker logs child.
    #
    nohup setsid "$SCRIPT_PATH" --run >> "$WATCHER_LOG" 2>&1 &

    #
    # The background instance writes its own PID once initialized.
    #
    for _ in {1..20}; do
        if is_running; then
            echo "Sandstorm watcher started (PID $(cat "$PID_FILE"))."
            echo "Log: $WATCHER_LOG"
            exit 0
        fi

        sleep 0.1
    done

    echo "ERROR: Watcher did not start."
    exit 1
}


stop_watcher() {
    if ! is_running; then
        echo "Sandstorm watcher is not running."
        rm -f "$PID_FILE"
        exit 1
    fi

    local pid
    pid="$(cat "$PID_FILE")"

    echo "Stopping Sandstorm watcher (PID $pid)..."

    #
    # Kill the entire process group. The negative PID means process group.
    # This also terminates the attached `docker logs --follow`.
    #
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null

    for _ in {1..20}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo "Sandstorm watcher stopped."
            exit 0
        fi

        sleep 0.1
    done

    echo "Watcher did not stop cleanly; forcing termination..."
    kill -9 -- "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null

    rm -f "$PID_FILE"

    echo "Sandstorm watcher stopped."
}


status_watcher() {
    if is_running; then
        echo "Sandstorm watcher is running (PID $(cat "$PID_FILE"))."
    else
        echo "Sandstorm watcher is not running."
        rm -f "$PID_FILE"
    fi
}


cleanup() {
    rm -f "$PID_FILE"
}


# ----------------------------------------------------------------------
# Watcher functions
# ----------------------------------------------------------------------

load_users() {
    PLAYER_NAMES=()
    DISCORD_TAGS=()

    while IFS=$'\t' read -r steam_id player_name discord_tag; do
        PLAYER_NAMES["$steam_id"]="$player_name"
        DISCORD_TAGS["$steam_id"]="$discord_tag"
    done < <(
        jq -r '
            .users[]
            | [.steam_id, .player_name, .discord_tag]
            | @tsv
        ' "$USERS_FILE"
    )
}

notify() {
    local message="$1"
    local notification="${2:-silent}"

    echo "$(date): $message"

    if [[ "$notification" == "notify" ]]; then
        "$DISCORD_SCRIPT" --notify "$message"
    else
        "$DISCORD_SCRIPT" "$message"
    fi
}

find_active_steam_id_by_name() {
    local search_name="$1"
    local id

    for id in "${!ACTIVE_USERS[@]}"; do
        if [[ "${ACTIVE_USERS[$id]}" == "$search_name" ]]; then
            echo "$id"
            return 0
        fi
    done

    return 1
}

process_line() {
    local line="$1"
    local name
    local steam_id
    local known_name
    local discord_tag
    local now
    # kill tracking
    local victim
    local killer
    local kill_time
    local victim_steam_id
    local killer_steam_id
    local victim_display
    local killer_display
    local victims
    # map tracking
    local map
    local internal_map
    local scenario
    local mode
    local side
    local lighting


    #
    # Login request
    #
    if [[ "$line" =~ Login\ request:\ \?Name=(.*)\ userId:\ SteamNWI:([0-9]+)\ platform: ]]; then
        name="${BASH_REMATCH[1]}"
        steam_id="${BASH_REMATCH[2]}"

        PENDING_USERS["$name"]="$steam_id"

        if [[ -n "${PLAYER_NAMES[$steam_id]-}" ]]; then
            echo "Known player login request: $name ($steam_id)"
        else
            echo "Other player login request: $name ($steam_id)"
        fi

        return
    fi


    #
    # Successful join
    #
    if [[ "$line" =~ LogNet:\ Join\ succeeded:\ (.*)$ ]]; then
        name="${BASH_REMATCH[1]}"
        name="${name%$'\r'}"

        steam_id="${PENDING_USERS[$name]-}"

        [[ -z "$steam_id" ]] && return

        unset 'PENDING_USERS[$name]'

        # Avoid duplicate join notifications.
        [[ -n "${ACTIVE_USERS[$steam_id]-}" ]] && return

        #
        # Track EVERY human player, known or unknown.
        #
        ACTIVE_USERS["$steam_id"]="$name"

        #
        # Known player
        #
        if [[ -n "${PLAYER_NAMES[$steam_id]-}" ]]; then

            known_name="${PLAYER_NAMES[$steam_id]}"
            discord_tag="${DISCORD_TAGS[$steam_id]-}"

            #
            # This also lets us notice if a known player changes
            # their Steam display name.
            #
            if [[ "$name" != "$known_name" ]]; then
                notify "🟢 $discord_tag joined the server as **$name**" notify
            else
                notify "🟢 $discord_tag joined the server" notify
            fi

        #
        # Everyone else
        #
        else
            notify "👤 '**$name**' joined the server"
        fi

        return
    fi

    #
    # Kill event - victim
    #
    # Example:
    # [DoubleKillProtection] Removing PlayerState=LouiSypher at Time=39609.691
    #
    if [[ "$line" =~ \[DoubleKillProtection\]\ Removing\ PlayerState=(.*)\ at\ Time=([0-9.]+) ]]; then
        victim="${BASH_REMATCH[1]}"
        kill_time="${BASH_REMATCH[2]}"

        #
        # Multiple victims can share the same timestamp, so accumulate them.
        #
        if [[ -n "${PENDING_KILL_VICTIMS[$kill_time]-}" ]]; then
            PENDING_KILL_VICTIMS["$kill_time"]+=$'\n'"$victim"
        else
            PENDING_KILL_VICTIMS["$kill_time"]="$victim"
        fi

        return
    fi


    #
    # Kill event - killer
    #
    # Example:
    # [DoubleKillProtection] Registered kill: PlayerState=telnetdoogie at Time=39609.691
    #
    if [[ "$line" =~ \[DoubleKillProtection\]\ Registered\ kill:\ PlayerState=(.*)\ at\ Time=([0-9.]+) ]]; then
        killer="${BASH_REMATCH[1]}"
        kill_time="${BASH_REMATCH[2]}"

        victims="${PENDING_KILL_VICTIMS[$kill_time]-}"
        unset 'PENDING_KILL_VICTIMS[$kill_time]'

        [[ -z "$victims" ]] && return

        #
        # Is the killer a currently-connected human?
        # If not, they're a bot and we don't notify.
        #
        killer_steam_id="$(find_active_steam_id_by_name "$killer")"

        [[ -z "$killer_steam_id" ]] && return

        #
        # Determine how to display the killer.
        # Known players get a Discord mention.
        # Unknown humans get their in-game name.
        #
        if [[ -n "${PLAYER_NAMES[$killer_steam_id]-}" ]]; then
            killer_display="${DISCORD_TAGS[$killer_steam_id]}"
        else
            killer_display="**$killer**"
        fi


        #
        # There may be more than one victim with this timestamp.
        #
        while IFS= read -r victim; do

            [[ -z "$victim" ]] && continue

            #
            # Is the victim also a currently-connected human?
            #
            victim_steam_id="$(find_active_steam_id_by_name "$victim")"

            #
            # No human match means it was a bot.
            #
            [[ -z "$victim_steam_id" ]] && continue

            #
            # Ignore weird self-kill cases for now.
            #
            [[ "$victim_steam_id" == "$killer_steam_id" ]] && continue

            #
            # Known victims get their Discord mention too.
            #
            if [[ -n "${PLAYER_NAMES[$victim_steam_id]-}" ]]; then
                victim_display="${DISCORD_TAGS[$victim_steam_id]}"
            else
                victim_display="**$victim**"
            fi

            notify "☠️ $victim_display was killed by $killer_display"

        done <<< "$victims"

        return
    fi

    #
    # Map change / server travel
    #
    # Examples:
    #
    # Forest?scenario=Scenario_Forest_Checkpoint_Security?Lighting=Day
    #
    # Compound?Scenario=Scenario_Outskirts_Checkpoint_Insurgents?Game=Checkpoint?Lighting=Day?
    #
    if [[ "$line" =~ ProcessServerTravel:\ ([^?]+)\?[Ss]cenario=([^?]+) ]]; then

        internal_map="${BASH_REMATCH[1]}"
        scenario="${BASH_REMATCH[2]}"

        #
        # Lighting may appear anywhere later in the travel URL.
        #
        lighting="Unknown"

        if [[ "$line" =~ \?[Ll]ighting=([^?\ ]+) ]]; then
            lighting="${BASH_REMATCH[1]}"
        fi

        #
        # Remove Scenario_ prefix:
        #
        # Scenario_Forest_Checkpoint_Security
        # becomes:
        # Forest_Checkpoint_Security
        #
        scenario="${scenario#Scenario_}"

        #
        # Parse:
        #
        # Forest_Checkpoint_Security
        # Outskirts_Checkpoint_Insurgents
        #
        # The first capture is intentionally greedy so map names
        # containing underscores will still work.
        #
        if [[ "$scenario" =~ ^(.+)_([^_]+)_(Security|Insurgents)$ ]]; then
            map="${BASH_REMATCH[1]}"
            mode="${BASH_REMATCH[2]}"
            side="${BASH_REMATCH[3]}"
        else
            #
            # Unexpected scenario format.
            #
            map="$internal_map"
            mode="Unknown"
            side="Unknown"
        fi

        notify "🗺️ Map changing to: **$map** — $mode / $side / $lighting"

        return
    fi


    #
    # Disconnect
    #
    if [[ "$line" =~ UChannel::Close:.*IsServer:\ YES.*UniqueId:\ SteamNWI:([0-9]+) ]]; then
        steam_id="${BASH_REMATCH[1]}"

        #
        # Capture the active name and remove EVERY human from
        # ACTIVE_USERS, whether they're known or unknown.
        #
        name="${ACTIVE_USERS[$steam_id]-}"
        unset 'ACTIVE_USERS[$steam_id]'

        #
        # We currently only send leave notifications for known players.
        #
        [[ -z "${PLAYER_NAMES[$steam_id]-}" ]] && return

        now=$SECONDS

        if [[ -n "${LAST_LEAVE[$steam_id]-}" ]]; then
            if (( now - LAST_LEAVE[$steam_id] < 10 )); then
                return
            fi
        fi

        LAST_LEAVE["$steam_id"]=$now

        known_name="${PLAYER_NAMES[$steam_id]}"
        discord_tag="${DISCORD_TAGS[$steam_id]-}"

        #
        # If for some reason we didn't have the active player name,
        # fall back to the configured known name.
        #
        [[ -z "$name" ]] && name="$known_name"

        if [[ "$name" != "$known_name" ]]; then
            notify "🔴 $discord_tag (**$name**) left the server"
        else
            notify "🔴 $discord_tag left the server"
        fi

        return
    fi
}


run_watcher() {
    #
    # Prevent accidentally starting a second daemon manually.
    #
    if is_running && [[ "$(cat "$PID_FILE")" != "$$" ]]; then
        echo "ERROR: Watcher is already running (PID $(cat "$PID_FILE"))."
        exit 1
    fi

    echo "$$" > "$PID_FILE"

    trap cleanup EXIT
    trap 'exit 0' INT TERM HUP

    if ! command -v jq >/dev/null 2>&1; then
        echo "ERROR: jq is required."
        exit 1
    fi

    if [[ ! -f "$USERS_FILE" ]]; then
        echo "ERROR: Users file not found: $USERS_FILE"
        exit 1
    fi

    if [[ ! -x "$DISCORD_SCRIPT" ]]; then
        echo "ERROR: Discord script is not executable: $DISCORD_SCRIPT"
        exit 1
    fi

    load_users

    echo "$(date): Watching Docker container: $CONTAINER"
    echo "$(date): Loaded ${#PLAYER_NAMES[@]} known users."

    while true; do

        while IFS= read -r line; do
            process_line "$line"
        done < <(
            docker logs \
                --follow \
                --tail 0 \
                "$CONTAINER" 2>&1
        )

        echo "$(date): Docker log stream ended. Reconnecting in 2 seconds..."

        PENDING_USERS=()
        ACTIVE_USERS=()

        sleep 2
    done
}


# ----------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------

case "${1:-}" in

    -start)
        start_watcher
        ;;

    -stop)
        stop_watcher
        ;;

    -status)
        status_watcher
        ;;

    --run)
        run_watcher
        ;;

    *)
        echo "Usage:"
        echo "  $0 -start"
        echo "  $0 -stop"
        echo "  $0 -status"
        exit 1
        ;;

esac