#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-5177}"
HOST="${HOST:-127.0.0.1}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
PYTHON_BIN="${PYTHON:-python3}"
if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

mkdir -p "$RUN_DIR"

# Linux commonly provides setsid; macOS Bash can create a process group for
# background jobs when job control is enabled.
launch_in_session() {
  local log_file="$1"
  local command="$2"
  shift 2

  if command -v setsid >/dev/null 2>&1; then
    setsid bash -c "$command" _ "$@" >"$log_file" 2>&1 &
  else
    set -m
    bash -c "$command" _ "$@" >"$log_file" 2>&1 &
    set +m
  fi

  echo $!
}

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
  local pid
  pid="$(launch_in_session "$log_file" '
    cd "$1"
    exec "$2" -m uvicorn app.main:app --app-dir backend --host "$3" --port "$4"
  ' "$ROOT_DIR" "$PYTHON_BIN" "$HOST" "$BACKEND_PORT")"

  echo "$pid" > "$pid_file"
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
  local pid
  pid="$(launch_in_session "$log_file" '
    cd "$1/frontend"
    export VITE_API_TARGET="$2"
    exec npm exec vite -- --host "$3" --port "$4"
  ' "$ROOT_DIR" "${VITE_API_TARGET:-http://$HOST:$BACKEND_PORT}" "$FRONTEND_HOST" "$FRONTEND_PORT")"

  echo "$pid" > "$pid_file"
  echo "Frontend started: http://localhost:$FRONTEND_PORT (pid $(cat "$pid_file"))"
  echo "Frontend log: $log_file"
}

start_backend
start_frontend

echo "Services are starting. Use ./stop.sh to stop them."
