#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from apps.ops.project_state_consistency_guard import generate_project_state_consistency_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check consistency between features.json and progress.txt and emit a CI-friendly report.",
    )
    parser.add_argument("--features", default="docs/projects/current/features.json", help="features.json path")
    parser.add_argument("--progress", default="docs/projects/current/progress.txt", help="progress.txt path")
    parser.add_argument(
        "--output",
        default="artifacts/qa/project_state_consistency_guard.json",
        help="Output JSON report path",
    )
    parser.add_argument("--generated-at-utc", default=None, help="Optional UTC timestamp override")
    parser.add_argument(
        "--allow-summary-pending",
        action="store_true",
        help="Allow done/count mismatch while a trailing Summary line indicates checkpoint is pending",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = generate_project_state_consistency_report(
        features_path=args.features,
        progress_path=args.progress,
        output_path=args.output,
        generated_at_utc=args.generated_at_utc,
        allow_summary_pending=args.allow_summary_pending,
    )

    status = str(report.get("status", "fail"))
    mismatch_count = int(report.get("mismatch_count", 0))
    warning_count = int(report.get("warning_count", 0))
    print(f"project_state={status} mismatches={mismatch_count} warnings={warning_count} report={Path(args.output)}")

    for mismatch in report.get("mismatches", []):
        if isinstance(mismatch, dict):
            print(f"mismatch[{mismatch.get('code', 'unknown')}]: {mismatch.get('message', '')}")
    for warning in report.get("warnings", []):
        if isinstance(warning, dict):
            print(f"warning[{warning.get('code', 'unknown')}]: {warning.get('message', '')}")

    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
