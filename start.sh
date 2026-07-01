#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
HOST="${HOST:-127.0.0.1}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"

mkdir -p "$RUN_DIR"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

start_backend() {
  local pid_file="$RUN_DIR/backend.pid"
  local log_file="$RUN_DIR/backend.log"

  if is_running "$pid_file"; then
    echo "Backend already running on pid $(cat "$pid_file")."
    return
  fi

  rm -f "$pid_file"
  setsid bash -c '
    cd "$1"
    exec python3 -m uvicorn app.main:app --app-dir backend --host "$2" --port "$3"
  ' _ "$ROOT_DIR" "$HOST" "$BACKEND_PORT" >"$log_file" 2>&1 &

  echo $! > "$pid_file"
  echo "Backend started: http://$HOST:$BACKEND_PORT (pid $(cat "$pid_file"))"
  echo "Backend log: $log_file"
}

start_frontend() {
  local pid_file="$RUN_DIR/frontend.pid"
  local log_file="$RUN_DIR/frontend.log"

  if is_running "$pid_file"; then
    echo "Frontend already running on pid $(cat "$pid_file")."
    return
  fi

  rm -f "$pid_file"
  setsid bash -c '
    cd "$1/frontend"
    export VITE_API_TARGET="$2"
    exec npm exec vite -- --host "$3" --port "$4"
  ' _ "$ROOT_DIR" "${VITE_API_TARGET:-http://$HOST:$BACKEND_PORT}" "$FRONTEND_HOST" "$FRONTEND_PORT" >"$log_file" 2>&1 &

  echo $! > "$pid_file"
  echo "Frontend started: http://localhost:$FRONTEND_PORT (pid $(cat "$pid_file"))"
  echo "Frontend log: $log_file"
}

start_backend
start_frontend

echo "Services are starting. Use ./stop.sh to stop them."
