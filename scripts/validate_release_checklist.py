#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

REQUIRED_TOP_LEVEL_FIELDS = (
    "version_tag",
    "release_approved_by",
    "release_approved_at_utc",
    "release_approval_log",
    "checks",
)

REQUIRED_CHECKS = (
    "api_tests_passed",
    "web_tests_passed",
    "worker_tests_passed",
    "e2e_tests_passed",
    "perf_security_smoke_passed",
    "migration_reviewed",
    "rollback_plan_verified",
)


def _validate(path: Path) -> list[str]:
    if not path.exists():
        return [f"checklist file not found: {path}"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid json: {exc}"]

    errors: list[str] = []
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    version_tag = str(payload.get("version_tag", "")).strip()
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version_tag):
        errors.append("version_tag must match vX.Y.Z")

    approved_by = str(payload.get("release_approved_by", "")).strip()
    if not approved_by:
        errors.append("release_approved_by must not be empty")

    approved_at = str(payload.get("release_approved_at_utc", "")).strip()
    if not approved_at:
        errors.append("release_approved_at_utc must not be empty")

    approval_log = str(payload.get("release_approval_log", "")).strip()
    if not approval_log:
        errors.append("release_approval_log must not be empty")

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be an object")
        return errors

    for key in REQUIRED_CHECKS:
        if checks.get(key) is not True:
            errors.append(f"required checklist item is not completed: checks.{key}")

    return errors


def main(argv: list[str]) -> int:
    checklist_path = Path(argv[1]) if len(argv) > 1 else Path("docs/release/beta-release-checklist.json")
    errors = _validate(checklist_path)

    if errors:
        print("Release checklist validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Release checklist validation passed: {checklist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
