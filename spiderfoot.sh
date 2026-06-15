#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR}"

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

LOCK_FILE="/tmp/spiderfoot-llm.lock"
LOG_FILE="${HOME}/.spiderfoot/launcher.log"
URL="http://127.0.0.1:5001"
PING_URL="${URL}/scananalyzellmping"

mkdir -p "${HOME}/.spiderfoot"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "${LOG_FILE}"
}

notify() {
    local title="$1"
    local body="$2"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "${title}" "${body}" 2>/dev/null || true
    fi
}

llm_ready() {
    curl -sf "${PING_URL}" 2>/dev/null | grep -q '"llm_version"'
}

open_ui() {
    local opened=0

    log "Attempting to open browser at ${URL}/"

    if command -v xdg-open >/dev/null 2>&1; then
        if xdg-open "${URL}/" >/dev/null 2>&1; then
            opened=1
        fi
    fi

    if [ "${opened}" -eq 0 ] && command -v gio >/dev/null 2>&1; then
        if gio open "${URL}/" >/dev/null 2>&1; then
            opened=1
        fi
    fi

    if [ "${opened}" -eq 0 ] && command -v sensible-browser >/dev/null 2>&1; then
        if sensible-browser "${URL}/" >/dev/null 2>&1 & then
            opened=1
        fi
    fi

    if [ "${opened}" -eq 0 ]; then
        for browser in firefox chromium google-chrome brave-browser; do
            if command -v "${browser}" >/dev/null 2>&1; then
                "${browser}" "${URL}/" >/dev/null 2>&1 &
                opened=1
                break
            fi
        done
    fi

    if [ "${opened}" -eq 1 ]; then
        log "Browser opened successfully"
        notify "SpiderFoot OSINT" "Opened ${URL}"
        return 0
    fi

    log "Failed to open browser automatically"
    notify "SpiderFoot OSINT" "Open ${URL} in your browser"
    echo "Could not open a browser automatically."
    echo "Open this URL manually: ${URL}/"
    return 1
}

stop_existing() {
    if pgrep -f "python3 ./sf.py -l" >/dev/null 2>&1; then
        log "Stopping existing SpiderFoot web UI"
        echo "Stopping existing SpiderFoot web UI..."
        pkill -TERM -f "python3 ./sf.py -l" >/dev/null 2>&1 || true
        sleep 2
    fi

    if pgrep -f "startSpiderFootScanner" >/dev/null 2>&1; then
        log "Stopping orphaned SpiderFoot scan workers"
        echo "Stopping orphaned SpiderFoot scan workers..."
        pkill -TERM -f "startSpiderFootScanner" >/dev/null 2>&1 || true
        sleep 1
    fi

    if command -v fuser >/dev/null 2>&1 && fuser 5001/tcp >/dev/null 2>&1; then
        log "Freeing port 5001"
        echo "Freeing port 5001..."
        fuser -k 5001/tcp >/dev/null 2>&1 || true
        sleep 1
    fi
}

wait_for_llm_ready() {
    local attempt
    for attempt in $(seq 1 45); do
        if llm_ready; then
            return 0
        fi
        sleep 1
    done
    return 1
}

finish_launcher() {
    local message="$1"
    echo "${message}"
    log "${message}"
    notify "SpiderFoot OSINT" "${message}"
    if [ -t 1 ]; then
        echo
        echo "Press Enter to close this window."
        read -r _
    fi
}

already_running() {
    finish_launcher "SpiderFoot is already running. Opening browser..."
    open_ui || true
}

start_server() {
    stop_existing

    if [ ! -f "${APP_DIR}/sf/bin/activate" ]; then
        log "Virtualenv missing at ${APP_DIR}/sf/bin/activate"
        notify "SpiderFoot OSINT" "Setup missing. Run spiderfoot setup first."
        echo "SpiderFoot virtualenv not found at ${APP_DIR}/sf"
        echo "Check ${LOG_FILE} for details."
        exit 1
    fi

    # shellcheck disable=SC1091
    source "${APP_DIR}/sf/bin/activate"

    echo "Starting SpiderFoot with LLM analysis support..."
    echo "Reports save to: ${APP_DIR}/reports/"
    log "Starting SpiderFoot server"

    (
        if wait_for_llm_ready; then
            log "LLM endpoint ready"
            echo "LLM analysis ready. Opening browser..."
            open_ui || true
        else
            log "LLM endpoint not ready after wait"
            echo "SpiderFoot started, but LLM endpoint is still warming up."
            echo "Open ${URL}/ and hard-refresh the Scans page (Ctrl+Shift+R)."
            open_ui || true
        fi
    ) &

    exec python3 "${APP_DIR}/sf.py" -l 127.0.0.1:5001
}

main() {
    log "Desktop launcher invoked from ${APP_DIR}"

    exec 9>"${LOCK_FILE}"
    if ! flock -n 9; then
        already_running
        exit 0
    fi

    if llm_ready; then
        already_running
        exit 0
    fi

    start_server
}

main "$@"