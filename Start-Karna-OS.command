#!/usr/bin/env bash
# ---------------------------------------------------------------
#  Karna OS one-click launcher for macOS
#  First run: installs everything (needs Python, ~2-3 minutes).
#  Every run after: starts the app and opens your browser.
#  Keep the Terminal window open while using Karna OS; closing
#  the window stops the app.
# ---------------------------------------------------------------
cd "$(dirname "$0")" || exit 1
PORT="${KARNA_PORT:-8000}"

# Already running from this folder? (marker remembers the port)
if [ -f .karna_port ]; then
  LASTPORT=$(tr -d '[:space:]' < .karna_port)
  if [ -n "$LASTPORT" ] && curl -s --max-time 2 "http://127.0.0.1:$LASTPORT/" | grep -qi "Karna"; then
    echo "Karna OS is already running - opening it."
    open "http://127.0.0.1:$LASTPORT/"
    exit 0
  fi
fi

# Pick a usable Python: 3.11-3.13 (our pinned libraries need this range).
PYBIN=""
for cand in python3.12 python3.13 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    V=$("$cand" -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
    case "$V" in
      3.11|3.12|3.13) PYBIN="$cand"; break ;;
    esac
  fi
done

if [ -z "$PYBIN" ]; then
  echo ""
  echo "  Karna OS needs Python 3.11, 3.12 or 3.13."
  echo ""
  echo "  OPTION A - easiest, nothing to download:"
  echo "    Open Terminal (Apps > Utilities > Terminal) and type:"
  echo "        xcode-select --install"
  echo "    Approve the window that appears. It installs Python in ~1 minute."
  echo ""
  echo "  OPTION B - install Python 3.12 from the page that is opening,"
  echo "  then double-click this file again."
  echo ""
  open "https://www.python.org/downloads/release/python-3128/" 2>/dev/null \
    || echo "  Visit: https://www.python.org/downloads/release/python-3128/"
  echo "  Press Enter to close this window..."
  read -r _
  exit 1
fi

# First run: set up the virtual environment.
if [ ! -x ".venv/bin/python" ]; then
  echo ""
  echo "  First run: setting up Karna OS - one time only, 1-3 minutes..."
  echo ""
  "$PYBIN" -m venv .venv
  ./.venv/bin/python -m pip install --upgrade pip --quiet
  ./.venv/bin/python -m pip install -r requirements.txt --quiet
  echo "  Setup complete."
  echo ""
fi

[ -f .env ] || cp .env.example .env

# Self-heal: an interrupted first install leaves a broken venv.
if ! ./.venv/bin/python -c "import uvicorn, fastapi" >/dev/null 2>&1; then
  echo "  Finishing setup (this happens if a previous run was interrupted)..."
  ./.venv/bin/python -m pip install -r requirements.txt --quiet
fi

# Port occupied by some other program? Step aside until one is free.
if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  ORIG="$PORT"
  while lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do
    PORT=$((PORT + 1))
  done
  echo "  Port $ORIG is used by another program - using port $PORT instead."
fi

echo "  Starting Karna OS..."
( sleep 4; open "http://127.0.0.1:$PORT/" 2>/dev/null ) &
echo "$PORT" > .karna_port

echo ""
echo "  Karna OS is running: http://127.0.0.1:$PORT/"
echo ""
echo "  - Keep this window open while you use Karna OS."
echo "  - To stop it: close this window (or press Ctrl+C)."
echo "  - Your data stays in the \"data\" folder on this computer."
echo "    Nothing is uploaded anywhere. Delete the folder to erase everything."
echo ""
exec ./.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT"
