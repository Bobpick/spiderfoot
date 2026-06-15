#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

LOCK_FILE="/tmp/spiderfoot-llm.lock"
URL="http://127.0.0.1:5001"
PING_URL="${URL}/scananalyzellmping"

llm_ready() {
    curl -sf "${PING_URL}" 2>/dev/null | grep -q '"llm_version"'
}

open_ui() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "${URL}/"
    fi
}

stop_existing() {
    if pgrep -f "python3 ./sf.py -l" >/dev/null 2>&1; then
        echo "Stopping existing SpiderFoot web UI..."
        pkill -TERM -f "python3 ./sf.py -l" >/dev/null 2>&1 || true
        sleep 2
    fi

    if pgrep -f "startSpiderFootScanner" >/dev/null 2>&1; then
        echo "Stopping orphaned SpiderFoot scan workers..."
        pkill -TERM -f "startSpiderFootScanner" >/dev/null 2>&1 || true
        sleep 1
    fi

    if command -v fuser >/dev/null 2>&1; then
        if fuser 5001/tcp >/dev/null 2>&1; then
            echo "Freeing port 5001..."
            fuser -k 5001/tcp >/dev/null 2>&1 || true
            sleep 1
        fi
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

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    echo "SpiderFoot is already starting. Opening browser..."
    open_ui
    exit 0
fi

if llm_ready; then
    echo "SpiderFoot LLM edition is already running."
    open_ui
    exit 0
fi

stop_existing

source sf/bin/activate

echo "Starting SpiderFoot with LLM analysis support..."
echo "Reports save to: $(pwd)/reports/"

(
    if wait_for_llm_ready; then
        echo "LLM analysis ready. Opening browser..."
        open_ui
    else
        echo "Warning: SpiderFoot started but LLM endpoint is not responding yet."
        echo "Wait a few seconds, then refresh the Scans page (Ctrl+Shift+R)."
        open_ui
    fi
) &

exec python3 ./sf.py -l 127.0.0.1:5001