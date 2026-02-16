#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/bootstrap_common.sh"

cd "${REPO_ROOT}"
TARGET="migrate"

require_env_vars "${TARGET}"

if python3 - <<'PY'
from apps.infra.migrations.runner import upgrade_head
from apps.infra.postgres import initialize_database_runtime

runtime = initialize_database_runtime(request_id="bootstrap-migrate")
upgrade_head(runtime.engine)
print("migration_ok")
PY
then
  bootstrap_log "${TARGET}" "run_migrations" "ok"
else
  bootstrap_log "${TARGET}" "run_migrations" "failed"
  exit 1
fi

bootstrap_log "${TARGET}" "completed" "ok"
