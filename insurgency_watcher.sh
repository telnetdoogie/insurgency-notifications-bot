#!/usr/bin/env bash

CONTAINER="insurgency-sandstorm"
USERS_FILE="./users.json"
DISCORD_SCRIPT="./sendToDiscord.sh"

PID_FILE="/tmp/sandstorm-watcher.pid"
WATCHER_LOG="/tmp/sandstorm-watcher.log"

SCRIPT_PATH="$(readlink -f "$0")"

declare -A KNOWN_USERS
declare -A PENDING_USERS
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
    KNOWN_USERS=()

    while IFS=$'\t' read -r steam_id label; do
        KNOWN_USERS["$steam_id"]="$label"
    done < <(
        jq -r 'to_entries[] | [.key, .value] | @tsv' "$USERS_FILE"
    )
}


notify() {
    local message="$1"

    echo "$(date): $message"
    "$DISCORD_SCRIPT" "$message"
}


process_line() {
    local line="$1"
    local name
    local steam_id
    local label
    local now


    #
    # Login request
    #
    if [[ "$line" =~ Login\ request:\ \?Name=(.*)\ userId:\ SteamNWI:([0-9]+)\ platform: ]]; then
        name="${BASH_REMATCH[1]}"
        steam_id="${BASH_REMATCH[2]}"

        PENDING_USERS["$name"]="$steam_id"

        if [[ -n "${KNOWN_USERS[$steam_id]-}" ]]; then
            echo "Recognized login request: $name ($steam_id)"
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

        # Ignore users we aren't watching.
        [[ -z "${KNOWN_USERS[$steam_id]-}" ]] && return

        # Avoid duplicate join notifications.
        [[ -n "${ACTIVE_USERS[$steam_id]-}" ]] && return

        ACTIVE_USERS["$steam_id"]="$name"

        label="${KNOWN_USERS[$steam_id]}"

        if [[ "$label" == "$name" ]]; then
            notify "🟢 $name joined the server"
        else
            notify "🟢 $label entered into battle"
        fi

        return
    fi


    #
    # Disconnect
    #
    if [[ "$line" =~ UChannel::Close:.*IsServer:\ YES.*UniqueId:\ SteamNWI:([0-9]+) ]]; then
        steam_id="${BASH_REMATCH[1]}"

        [[ -z "${KNOWN_USERS[$steam_id]-}" ]] && return

        now=$SECONDS

        if [[ -n "${LAST_LEAVE[$steam_id]-}" ]]; then
            if (( now - LAST_LEAVE[$steam_id] < 10 )); then
                return
            fi
        fi

        LAST_LEAVE["$steam_id"]=$now

        label="${KNOWN_USERS[$steam_id]}"
        name="${ACTIVE_USERS[$steam_id]-}"

        unset 'ACTIVE_USERS[$steam_id]'

        if [[ -n "$name" && "$name" != "$label" ]]; then
            notify "🔴 $label left the server"
        else
            notify "🔴 $label left the server"
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
    echo "$(date): Loaded ${#KNOWN_USERS[@]} watched users."

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