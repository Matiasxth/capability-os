#!/usr/bin/env bash
# CapOS launcher for Mac/Linux
# Usage: ./start.sh [--port 9000] [--background]

set -e
cd "$(dirname "$0")"

PORT=8000
BG=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port|-p)
            if [[ -z "$2" || ! "$2" =~ ^[0-9]+$ ]]; then
                echo "Error: --port requires a numeric value"
                exit 1
            fi
            PORT="$2"
            shift 2
            ;;
        --background|-b)
            BG=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./start.sh [--port 8000] [--background]"
            echo "  --port, -p PORT   Set HTTP port (default: 8000)"
            echo "  --background, -b  Run in background"
            exit 0
            ;;
        *)
            echo "Unknown option: $1 (try --help)"
            exit 1
            ;;
    esac
done

# Check if already running
if command -v lsof &>/dev/null && lsof -iTCP:"$PORT" -sTCP:LISTEN &>/dev/null; then
    echo "CapOS is already running on port $PORT"
    echo "Open http://127.0.0.1:$PORT"
    exit 0
fi

# Install deps if needed
if ! python3 -c "import bcrypt, jwt" 2>/dev/null; then
    echo "Installing Python dependencies..."
    pip3 install -r requirements.txt
fi

if [ ! -d "system/frontend/app/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd system/frontend/app && npm install && npm run build && cd ../../..
elif [ ! -d "system/frontend/app/dist" ]; then
    echo "Building frontend..."
    cd system/frontend/app && npm run build && cd ../../..
fi

if $BG; then
    echo "Starting CapOS in background on port $PORT..."
    nohup python3 -m capabilityos serve --port "$PORT" > /tmp/capos.log 2>&1 &
    sleep 2
    echo "PID: $!"
    echo "Log: /tmp/capos.log"
    echo "Open http://127.0.0.1:$PORT"
    # Try to open browser
    if command -v open &>/dev/null; then open "http://127.0.0.1:$PORT";
    elif command -v xdg-open &>/dev/null; then xdg-open "http://127.0.0.1:$PORT"; fi
else
    echo "Starting CapOS on port $PORT..."
    python3 -m capabilityos serve --port "$PORT"
fi
