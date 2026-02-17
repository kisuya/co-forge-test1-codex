#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

API_HOST="${OMS_DEV_API_HOST:-127.0.0.1}"
API_PORT="${OMS_DEV_API_PORT:-18001}"
WEB_HOST="${OMS_DEV_WEB_HOST:-127.0.0.1}"
WEB_PORT="${OMS_DEV_WEB_PORT:-13002}"
START_WEB="${OMS_DEV_START_WEB:-0}"

API_PID_FILE="/tmp/oh-my-stock-api.pid"
WEB_PID_FILE="/tmp/oh-my-stock-web.pid"
API_LOG="/tmp/oh-my-stock-api.log"
WEB_LOG="/tmp/oh-my-stock-web.log"

usage() {
  cat <<'EOF'
Usage:
  scripts/manual_qa_stack.sh start   # Seed API adapter start (and web start if OMS_DEV_START_WEB=1)
  scripts/manual_qa_stack.sh stop    # Stop API/web processes and free ports
  scripts/manual_qa_stack.sh status  # Show listeners on QA ports
  scripts/manual_qa_stack.sh seed    # Seed only (no server)
EOF
}

kill_pid_file() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
    rm -f "${pid_file}"
  fi
}

kill_port_listener() {
  local port="$1"
  local pid
  pid="$(lsof -ti tcp:${port} || true)"
  if [[ -n "${pid}" ]]; then
    kill "${pid}" >/dev/null 2>&1 || true
  fi
}

wait_http_200() {
  local url="$1"
  local retries="${2:-30}"
  local sleep_sec="${3:-0.5}"
  for _ in $(seq 1 "${retries}"); do
    if curl -sS -o /dev/null -w "%{http_code}" "${url}" | grep -q '^200$'; then
      return 0
    fi
    sleep "${sleep_sec}"
  done
  return 1
}

start_api() {
  kill_pid_file "${API_PID_FILE}"
  kill_port_listener "${API_PORT}"

  nohup python "${REPO_ROOT}/scripts/dev_seeded_api_adapter.py" >"${API_LOG}" 2>&1 &
  local api_pid=$!
  echo "${api_pid}" >"${API_PID_FILE}"

  if ! wait_http_200 "http://${API_HOST}:${API_PORT}/health" 40 0.5; then
    echo "API start failed. Recent log:"
    tail -n 60 "${API_LOG}" || true
    exit 1
  fi
}

start_web() {
  kill_pid_file "${WEB_PID_FILE}"
  kill_port_listener "${WEB_PORT}"

  nohup env \
    NEXT_PUBLIC_API_BASE_URL="http://${API_HOST}:${API_PORT}" \
    NODE_OPTIONS="${NODE_OPTIONS:---localstorage-file=/tmp/oh-my-stock-node-localstorage}" \
    pnpm --dir "${REPO_ROOT}/apps/web" dev --hostname "${WEB_HOST}" --port "${WEB_PORT}" \
    >"${WEB_LOG}" 2>&1 &
  local web_pid=$!
  echo "${web_pid}" >"${WEB_PID_FILE}"

  if ! wait_http_200 "http://${WEB_HOST}:${WEB_PORT}" 60 0.5; then
    echo "Web start failed. Recent log:"
    tail -n 60 "${WEB_LOG}" || true
    exit 1
  fi
}

start_stack() {
  start_api
  if [[ "${START_WEB}" == "1" ]]; then
    start_web
  fi

  echo "Manual QA stack ready"
  echo "- API: http://${API_HOST}:${API_PORT}"
  if [[ "${START_WEB}" == "1" ]]; then
    echo "- Web: http://${WEB_HOST}:${WEB_PORT}"
  fi
  echo "- Test account: ${OMS_DEV_EMAIL:-kisu@test.com} / ${OMS_DEV_PASSWORD:-thekain007}"
  echo "- API log: ${API_LOG}"
  if [[ "${START_WEB}" == "1" ]]; then
    echo "- Web log: ${WEB_LOG}"
  fi
}

stop_stack() {
  kill_pid_file "${API_PID_FILE}"
  kill_pid_file "${WEB_PID_FILE}"
  kill_port_listener "${API_PORT}"
  kill_port_listener "${WEB_PORT}"
  echo "Manual QA stack stopped"
}

status_stack() {
  echo "--- API (${API_PORT}) ---"
  lsof -iTCP:${API_PORT} -sTCP:LISTEN -n -P || true
  echo "--- WEB (${WEB_PORT}) ---"
  lsof -iTCP:${WEB_PORT} -sTCP:LISTEN -n -P || true
}

seed_only() {
  python "${REPO_ROOT}/scripts/dev_seeded_api_adapter.py" --seed-only
}

case "${1:-start}" in
  start)
    start_stack
    ;;
  stop)
    stop_stack
    ;;
  status)
    status_stack
    ;;
  seed)
    seed_only
    ;;
  *)
    usage
    exit 1
    ;;
esac
