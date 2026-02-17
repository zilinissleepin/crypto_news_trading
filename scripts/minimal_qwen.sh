#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${ROOT_DIR}/.venv/bin/python"
PYTHONPATH_VALUE="libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:."
RUN_DIR="${ROOT_DIR}/.run/minimal-qwen"
LOG_DIR="${RUN_DIR}/logs"
PID_DIR="${RUN_DIR}/pids"
DEFAULT_REDIS_URL="redis://localhost:6379/14"

SERVICES=(
  "ingest-service"
  "entity-service"
  "llm-signal-service"
  "signal-fusion-service"
)

usage() {
  cat <<'EOF'
Usage:
  scripts/minimal_qwen.sh start [--redis-url URL] [--flush|--no-flush]
  scripts/minimal_qwen.sh stop
  scripts/minimal_qwen.sh status
  scripts/minimal_qwen.sh logs [service]

Examples:
  scripts/minimal_qwen.sh start
  scripts/minimal_qwen.sh start --redis-url redis://localhost:6379/14 --flush
  scripts/minimal_qwen.sh logs llm-signal-service
EOF
}

service_main_path() {
  local service="$1"
  echo "${ROOT_DIR}/services/${service}/main.py"
}

service_pid_path() {
  local service="$1"
  echo "${PID_DIR}/${service}.pid"
}

service_log_path() {
  local service="$1"
  echo "${LOG_DIR}/${service}.log"
}

is_running() {
  local service="$1"
  local pid_file
  pid_file="$(service_pid_path "$service")"
  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
    return 1
  fi

  local cmdline
  cmdline="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
  [[ "${cmdline}" == *"services/${service}/main.py"* ]]
}

require_venv() {
  if [[ ! -x "${VENV_PY}" ]]; then
    echo "ERROR: 未找到虚拟环境 Python: ${VENV_PY}"
    echo "请先执行: make uv-install"
    exit 1
  fi
}

check_redis() {
  local redis_url="$1"
  REDIS_URL="${redis_url}" "${VENV_PY}" - <<'PY'
import os
from redis import Redis

url = os.environ["REDIS_URL"]
r = Redis.from_url(url)
r.ping()
print(f"Redis OK: {url}")
PY
}

has_openai_key() {
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    return 0
  fi
  if [[ -f "${ROOT_DIR}/.env" ]] && grep -qE '^OPENAI_API_KEY=.+$' "${ROOT_DIR}/.env"; then
    return 0
  fi
  return 1
}

flush_redis_db() {
  local redis_url="$1"
  REDIS_URL="${redis_url}" "${VENV_PY}" - <<'PY'
import os
from redis import Redis

url = os.environ["REDIS_URL"]
r = Redis.from_url(url)
r.flushdb()
print(f"Redis DB flushed: {url}")
PY
}

start_service() {
  local service="$1"
  local redis_url="$2"
  local pid_file
  local log_file
  local main_py

  pid_file="$(service_pid_path "$service")"
  log_file="$(service_log_path "$service")"
  main_py="$(service_main_path "$service")"

  if is_running "$service"; then
    echo "[skip] ${service} already running (pid=$(cat "${pid_file}"))"
    return 0
  fi

  (
    cd "${ROOT_DIR}"
    REDIS_URL="${redis_url}" PYTHONPATH="${PYTHONPATH_VALUE}" \
      nohup "${VENV_PY}" "${main_py}" >"${log_file}" 2>&1 &
    echo $! >"${pid_file}"
  )

  sleep 0.4
  if is_running "$service"; then
    echo "[ok]   ${service} started (pid=$(cat "${pid_file}"))"
  else
    echo "[fail] ${service} failed to start, recent logs:"
    tail -n 50 "${log_file}" || true
    rm -f "${pid_file}"
    exit 1
  fi
}

stop_service() {
  local service="$1"
  local pid_file
  pid_file="$(service_pid_path "$service")"

  if ! is_running "$service"; then
    echo "[skip] ${service} not running"
    rm -f "${pid_file}"
    return 0
  fi

  local pid
  pid="$(cat "${pid_file}")"
  kill "${pid}" 2>/dev/null || true
  sleep 0.4

  if kill -0 "${pid}" 2>/dev/null; then
    kill -9 "${pid}" 2>/dev/null || true
  fi
  rm -f "${pid_file}"
  echo "[ok]   ${service} stopped"
}

show_status() {
  for service in "${SERVICES[@]}"; do
    local pid_file
    pid_file="$(service_pid_path "$service")"
    if is_running "$service"; then
      echo "[up]   ${service} pid=$(cat "${pid_file}") log=$(service_log_path "$service")"
    else
      echo "[down] ${service}"
    fi
  done
}

show_logs() {
  local target="${1:-}"
  if [[ -z "${target}" ]]; then
    echo "可选服务:"
    printf '  - %s\n' "${SERVICES[@]}"
    echo "示例: scripts/minimal_qwen.sh logs llm-signal-service"
    return 0
  fi

  local found=0
  for service in "${SERVICES[@]}"; do
    if [[ "${service}" == "${target}" ]]; then
      found=1
      break
    fi
  done
  if [[ "${found}" -eq 0 ]]; then
    echo "ERROR: 未知服务 ${target}"
    exit 1
  fi

  tail -f "$(service_log_path "${target}")"
}

cmd="${1:-}"
shift || true

mkdir -p "${LOG_DIR}" "${PID_DIR}"

case "${cmd}" in
  start)
    require_venv

    redis_url="${DEFAULT_REDIS_URL}"
    flush_mode="auto"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --redis-url)
          redis_url="${2:-}"
          shift 2
          ;;
        --flush)
          flush_mode="yes"
          shift
          ;;
        --no-flush)
          flush_mode="no"
          shift
          ;;
        *)
          echo "ERROR: 未知参数 $1"
          usage
          exit 1
          ;;
      esac
    done

    if ! has_openai_key; then
      echo "ERROR: 未检测到 OPENAI_API_KEY。"
      echo "请在环境变量或 ${ROOT_DIR}/.env 中设置 Qwen 兼容 API Key。"
      exit 1
    fi

    check_redis "${redis_url}"

    if [[ "${flush_mode}" == "yes" ]]; then
      flush_redis_db "${redis_url}"
    elif [[ "${flush_mode}" == "auto" ]]; then
      if [[ "${redis_url}" == "${DEFAULT_REDIS_URL}" ]]; then
        flush_redis_db "${redis_url}"
      else
        echo "Redis 未自动清空（自定义 URL）。如需清空请加 --flush。"
      fi
    fi

    echo "Starting minimal 4 services with Qwen..."
    echo "REDIS_URL=${redis_url}"
    for service in "${SERVICES[@]}"; do
      start_service "${service}" "${redis_url}"
    done
    echo "All services started."
    show_status
    ;;
  stop)
    for service in "${SERVICES[@]}"; do
      stop_service "${service}"
    done
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs "${1:-}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
