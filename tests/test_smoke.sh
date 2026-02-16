#!/bin/bash
[ -f "AGENTS.md" ] || { echo "FAIL: AGENTS.md missing"; exit 1; }
python3 -c "import json; json.load(open('.forge/projects/current/features.json'))" \
  || { echo "FAIL: features.json invalid"; exit 1; }
echo "Smoke test passed."
