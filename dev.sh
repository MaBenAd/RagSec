#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_READY_URL="http://127.0.0.1:8000/healthz"
BACKEND_DOCS_URL="http://127.0.0.1:8000/docs"
FRONTEND_URL="http://127.0.0.1:3000/login"
BACKEND_PID=""
FRONTEND_PID=""
PYTHON_BIN=""

ensure_env_file() {
  if [ ! -f "$ROOT_DIR/.env" ]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "Warning: .env was missing. A copy of .env.example has been created."
  fi
}

ensure_venv() {
  if [ -x "$ROOT_DIR/venv/bin/python3" ]; then
    PYTHON_BIN="$ROOT_DIR/venv/bin/python3"
    return 0
  fi

  echo "Creating virtual environment..."
  python3 -m venv "$ROOT_DIR/venv"
  PYTHON_BIN="$ROOT_DIR/venv/bin/python3"
}

ensure_backend_dependencies() {
  if "$PYTHON_BIN" -c "import uvicorn, dotenv, sqlalchemy, alembic" >/dev/null 2>&1; then
    return 0
  fi

  echo "Installing backend dependencies..."
  "$PYTHON_BIN" -m pip install -r "$ROOT_DIR/requirements.txt"
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local max_seconds="${3:-90}"

  for ((i=0; i<max_seconds; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Warning: $label is not ready after ${max_seconds}s."
  return 1
}

stop_docker_app_services() {
  docker compose stop backend frontend >/dev/null 2>&1 || true
}

stop_process_on_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$port" || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "$port"/tcp 2>/dev/null || true)"
  else
    return 0
  fi

  for pid in $pids; do
    if [ -n "$pid" ] && [ "$pid" != "$$" ]; then
      echo "Stopping existing process on port $port (PID $pid)..."
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done
}

cleanup() {
  echo "Stopping local frontend/backend..."
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$FRONTEND_PID" ]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  stop_process_on_port 8000
  stop_process_on_port 3000
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
ensure_env_file

echo "Starting Chatbot USMS development environment..."

command -v npm >/dev/null 2>&1 || { echo "Error: npm is required."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Error: docker is required."; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "Error: curl is required."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is required."; exit 1; }
docker info >/dev/null

ensure_venv
ensure_backend_dependencies

export PYTHONPATH=".:${PYTHONPATH:-}"
export QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
export RAG_EMBEDDING_BACKEND="${RAG_EMBEDDING_BACKEND:-hash}"
export ENABLE_EMOTION_LLM="${ENABLE_EMOTION_LLM:-false}"
export ENABLE_EDT_LLM="${ENABLE_EDT_LLM:-false}"
export ENABLE_TITLE_LLM="${ENABLE_TITLE_LLM:-false}"
export NEXT_PUBLIC_API_URL="http://127.0.0.1:8000"

echo "Starting Docker infrastructure (postgres, redis, qdrant)..."
docker compose up -d postgres redis qdrant --wait
stop_docker_app_services

if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$ROOT_DIR/frontend" && npm install --silent)
fi

echo "Bootstrapping shared dev content..."
"$PYTHON_BIN" backend/scripts/bootstrap_dev_content.py

stop_process_on_port 8000
stop_process_on_port 3000

echo "Starting backend on $BACKEND_DOCS_URL"
"$PYTHON_BIN" -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

echo "Starting frontend on $FRONTEND_URL"
(cd "$ROOT_DIR/frontend" && npm run dev -- --hostname 127.0.0.1 --port 3000) &
FRONTEND_PID=$!

echo "Waiting for services to be ready..."
wait_for_url "$BACKEND_READY_URL" "Backend"
wait_for_url "$FRONTEND_URL" "Frontend"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$FRONTEND_URL" >/dev/null 2>&1 || true
fi

echo "Services are running."
echo "Frontend: $FRONTEND_URL"
echo "Backend docs: $BACKEND_DOCS_URL"
echo "Press Ctrl+C to stop local frontend/backend. Docker infra will stay up."

while true; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "Warning: backend stopped. Shutting down local services."
    break
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "Warning: frontend stopped. Shutting down local services."
    break
  fi
  sleep 2
done
