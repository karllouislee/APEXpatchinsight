#!/usr/bin/env bash
set -u

cd "$(dirname "$0")" || exit 1

echo "=================================================="
echo "Apex Patch Insight"
echo "Foreground process: close this terminal or press Ctrl+C to stop."
echo "URL: http://127.0.0.1:8503"
echo "=================================================="

if [[ -x ".venv/Scripts/python.exe" ]]; then
  PYTHON_BIN=".venv/Scripts/python.exe"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  echo "[ERROR] Virtual environment Python was not found."
  read -r -p "Press Enter to close..."
  exit 1
fi

cleanup() {
  if [[ -n "${APP_PID:-}" ]]; then
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"$PYTHON_BIN" -m streamlit run app.py \
  --server.address=127.0.0.1 \
  --server.port=8503 \
  --server.headless=true \
  --server.fileWatcherType=none \
  --browser.gatherUsageStats=false &
APP_PID=$!
wait "$APP_PID"
APP_EXIT=$?
APP_PID=""

echo
echo "[STOPPED] Streamlit exited with code $APP_EXIT."
read -r -p "Press Enter to close..."
exit "$APP_EXIT"
