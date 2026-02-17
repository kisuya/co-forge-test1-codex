#!/bin/bash
set -euo pipefail

if [ -x "tests/test_smoke.sh" ]; then
  ./tests/test_smoke.sh "$@"
fi

python3 scripts/project_state_consistency_guard.py \
  --allow-summary-pending \
  --output /tmp/project_state_consistency_guard.json

python3 -m unittest discover -s tests -p "test_*.py"
