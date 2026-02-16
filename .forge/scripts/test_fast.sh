#!/bin/bash
set -euo pipefail

if [ -x "tests/test_smoke.sh" ]; then
  ./tests/test_smoke.sh "$@"
  exit 0
fi

echo "No fast test target found. Add tests and update .forge/scripts/test_fast.sh."
exit 1
