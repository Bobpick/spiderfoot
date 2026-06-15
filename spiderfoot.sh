#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Stop any existing SpiderFoot web UI on port 5001
if command -v fuser >/dev/null 2>&1; then
    if fuser 5001/tcp >/dev/null 2>&1; then
        echo "Stopping existing SpiderFoot instance on port 5001..."
        fuser -k 5001/tcp >/dev/null 2>&1 || true
        sleep 2
    fi
fi

source sf/bin/activate

echo "Starting SpiderFoot with LLM analysis support..."
echo "Reports save to: $(pwd)/reports/"

(sleep 4 && xdg-open http://127.0.0.1:5001) &

exec python3 ./sf.py -l 127.0.0.1:5001