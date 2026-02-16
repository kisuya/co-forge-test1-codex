#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/bootstrap_common.sh"

cd "${REPO_ROOT}"
TARGET="install"

require_env_vars "${TARGET}"
bootstrap_log "${TARGET}" "prepare_runtime" "ok"

if [[ "${BOOTSTRAP_RUN_INSTALL:-0}" == "1" ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv sync >/dev/null
    bootstrap_log "${TARGET}" "install_dependencies" "ok"
  else
    printf '[bootstrap/%s] uv not found in PATH\n' "${TARGET}"
    bootstrap_log "${TARGET}" "install_dependencies" "failed"
    exit 1
  fi
else
  bootstrap_log "${TARGET}" "install_dependencies" "skipped"
fi

bootstrap_log "${TARGET}" "completed" "ok"
