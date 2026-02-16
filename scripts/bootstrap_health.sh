#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/bootstrap_common.sh"

cd "${REPO_ROOT}"
TARGET="health"

require_env_vars "${TARGET}"

if python3 - <<'PY'
from apps.infra.postgres import initialize_database_runtime

runtime = initialize_database_runtime(request_id="bootstrap-health")
status = runtime.health(request_id="bootstrap-health")
print(status)
PY
then
  bootstrap_log "${TARGET}" "database_health" "ok"
else
  bootstrap_log "${TARGET}" "database_health" "failed"
  exit 1
fi

if [[ "${BOOTSTRAP_CHECK_REDIS:-0}" == "1" ]]; then
  if command -v redis-cli >/dev/null 2>&1 && redis-cli -u "${REDIS_URL}" ping >/dev/null 2>&1; then
    bootstrap_log "${TARGET}" "redis_health" "ok"
  else
    bootstrap_log "${TARGET}" "redis_health" "failed"
    exit 1
  fi
else
  bootstrap_log "${TARGET}" "redis_health" "skipped"
fi

bootstrap_log "${TARGET}" "completed" "ok"
