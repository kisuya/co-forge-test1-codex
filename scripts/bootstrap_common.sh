#!/usr/bin/env bash
set -euo pipefail

REQUIRED_ENV_VARS=(
  DATABASE_URL
  REDIS_URL
  JWT_SECRET
  SEC_USER_AGENT
  DART_API_KEY
  MARKET_DATA_API_KEY
)

bootstrap_log() {
  local target="$1"
  local step="$2"
  local status="$3"
  printf '[bootstrap/%s] step=%s status=%s\n' "$target" "$step" "$status"
}

require_env_vars() {
  local target="$1"
  local missing=0

  for name in "${REQUIRED_ENV_VARS[@]}"; do
    if [[ -z "${!name:-}" ]]; then
      printf '[bootstrap/%s] missing env var: %s\n' "$target" "$name"
      missing=1
    fi
  done

  if [[ "$missing" -ne 0 ]]; then
    bootstrap_log "$target" "validate_env" "failed"
    return 1
  fi

  bootstrap_log "$target" "validate_env" "ok"
}
