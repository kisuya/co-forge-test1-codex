#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from apps.ops.release_gate_policy import ReleaseGatePolicy
from apps.ops.release_gate_quality_bundle import generate_release_gate_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate contract/e2e/visual/KPI artifacts and compute release gate pass/fail.",
    )
    parser.add_argument("--artifact-dir", default="artifacts/qa", help="Directory containing gate artifacts")
    parser.add_argument("--output", default="artifacts/qa/release_gate_bundle.json", help="Output JSON report path")
    parser.add_argument("--generated-at-utc", default=None, help="Optional UTC timestamp override")
    parser.add_argument("--contract-artifact", default=None, help="Contract artifact filename")
    parser.add_argument("--e2e-artifact", default=None, help="E2E artifact filename")
    parser.add_argument("--visual-artifact", default=None, help="Visual regression artifact filename")
    parser.add_argument("--kpi-artifact", default=None, help="Product KPI artifact filename")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifact_files = {
        "contract": args.contract_artifact,
        "e2e": args.e2e_artifact,
        "visual_regression": args.visual_artifact,
        "product_kpi": args.kpi_artifact,
    }
    artifact_overrides = {key: value for key, value in artifact_files.items() if isinstance(value, str) and value.strip()}

    try:
        policy = ReleaseGatePolicy.from_env()
        report = generate_release_gate_report(
            artifact_dir=args.artifact_dir,
            output_path=args.output,
            artifact_files=artifact_overrides or None,
            policy=policy,
            generated_at_utc=args.generated_at_utc,
        )
    except ValueError as exc:
        print(f"release_gate=fail policy_error={exc}", file=sys.stderr)
        return 1

    release_gate = str(report.get("release_gate", "fail"))
    blocked = bool(report.get("blocked"))
    print(f"release_gate={release_gate} blocked={str(blocked).lower()} report={Path(args.output)}")
    if release_gate != "pass":
        for reason in report.get("failure_reasons", []):
            if isinstance(reason, dict):
                gate = str(reason.get("gate", "unknown"))
                code = str(reason.get("code", "unknown"))
                message = str(reason.get("message", ""))
                print(f"failure[{gate}] {code}: {message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
