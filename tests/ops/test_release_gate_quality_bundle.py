from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from apps.ops.release_gate_policy import ReleaseGatePolicy
from apps.ops.release_gate_quality_bundle import generate_release_gate_report


class ReleaseGateQualityBundleTests(unittest.TestCase):
    def test_generate_release_gate_report_pass_and_writes_single_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-gate-pass-") as tmpdir:
            artifact_dir = Path(tmpdir) / "qa"
            output_path = artifact_dir / "release_gate_bundle.json"
            self._write_gate_artifacts(
                artifact_dir,
                contract={"status": "pass", "failed_suites": [], "flaky_suites": []},
                e2e={"status": "pass", "failed_flows": [], "flaky_flows": []},
                visual={"status": "pass", "diff_ratio": 0.001, "threshold_ratio": 0.01},
                kpi=self._kpi_artifact(),
            )

            report = generate_release_gate_report(
                artifact_dir=artifact_dir,
                output_path=output_path,
                policy=self._policy(),
                generated_at_utc="2026-02-17T12:00:00Z",
            )

            self.assertEqual(report["release_gate"], "pass")
            self.assertFalse(report["blocked"])
            self.assertEqual(set(report["gate_results"].keys()), {"contract", "e2e", "visual_regression", "product_kpi"})
            for gate in report["gate_results"].values():
                self.assertEqual(gate["status"], "pass")
                self.assertEqual(gate["reason_codes"], [])
            self.assertEqual(report["failure_reasons"], [])
            self.assertTrue(output_path.exists())
            loaded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["release_gate"], "pass")
            self.assertIn("required quality gates", loaded["summary"])

    def test_generate_release_gate_report_fails_with_clear_failure_reasons(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-gate-fail-") as tmpdir:
            artifact_dir = Path(tmpdir) / "qa"
            output_path = artifact_dir / "release_gate_bundle.json"
            self._write_gate_artifacts(
                artifact_dir,
                contract={"status": "fail", "failed_suites": ["watchlist_contract"]},
                e2e={"status": "flaky", "flaky_flows": ["evidence_compare_flow"]},
                visual=None,
                kpi=self._kpi_artifact(
                    card_click_rate=0.05,
                    evidence_click_rate=0.10,
                    brief_open_rate=0.10,
                    inaccurate_reason_report_rate=0.60,
                    overall_low_confidence=True,
                ),
            )

            report = generate_release_gate_report(
                artifact_dir=artifact_dir,
                output_path=output_path,
                policy=self._policy(),
                generated_at_utc="2026-02-17T12:10:00Z",
            )

            self.assertEqual(report["release_gate"], "fail")
            self.assertTrue(report["blocked"])
            reasons = {(reason["gate"], reason["code"]) for reason in report["failure_reasons"]}
            self.assertIn(("contract", "suite_failed"), reasons)
            self.assertIn(("e2e", "flaky_result"), reasons)
            self.assertIn(("visual_regression", "missing_artifact"), reasons)
            self.assertIn(("product_kpi", "low_confidence"), reasons)
            self.assertIn(("product_kpi", "threshold_not_met"), reasons)
            for reason in report["failure_reasons"]:
                self.assertTrue(str(reason["message"]).strip())
            self.assertIn("visual_regression:missing_artifact", report["summary"])
            self.assertTrue(output_path.exists())

    def test_release_gate_cli_returns_non_zero_when_failed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-gate-cli-") as tmpdir:
            artifact_dir = Path(tmpdir) / "qa"
            output_path = artifact_dir / "release_gate_bundle.json"
            self._write_gate_artifacts(
                artifact_dir,
                contract={"status": "fail", "failed_suites": ["api_contract"]},
                e2e={"status": "pass"},
                visual={"status": "pass", "diff_ratio": 0.001, "threshold_ratio": 0.01},
                kpi=self._kpi_artifact(card_click_rate=0.01),
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/release_gate_quality_bundle.py",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 1)
            self.assertIn("release_gate=fail", proc.stdout)
            self.assertTrue(output_path.exists())
            loaded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["release_gate"], "fail")

    def _policy(self) -> ReleaseGatePolicy:
        return ReleaseGatePolicy(
            visual_max_diff_ratio=0.01,
            card_click_rate_min=0.20,
            evidence_click_rate_min=0.20,
            brief_open_rate_min=0.20,
            inaccurate_reason_report_rate_max=0.50,
            fail_on_flaky=True,
        )

    def _write_gate_artifacts(
        self,
        artifact_dir: Path,
        *,
        contract: dict[str, object] | None = None,
        e2e: dict[str, object] | None = None,
        visual: dict[str, object] | None = None,
        kpi: dict[str, object] | None = None,
    ) -> None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if contract is not None:
            (artifact_dir / "contract_smoke.json").write_text(
                json.dumps(contract, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        if e2e is not None:
            (artifact_dir / "e2e_smoke.json").write_text(
                json.dumps(e2e, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        if visual is not None:
            (artifact_dir / "visual_regression.json").write_text(
                json.dumps(visual, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        if kpi is not None:
            (artifact_dir / "product_kpi_smoke.json").write_text(
                json.dumps(kpi, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _kpi_artifact(
        self,
        *,
        card_click_rate: float = 0.75,
        evidence_click_rate: float = 0.66,
        brief_open_rate: float = 0.50,
        inaccurate_reason_report_rate: float = 0.33,
        overall_low_confidence: bool = False,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "generated_at_utc": "2026-02-17T11:00:00Z",
            "overall_low_confidence": overall_low_confidence,
            "metrics": {
                "card_click_rate": {"value": card_click_rate},
                "evidence_click_rate": {"value": evidence_click_rate},
                "brief_open_rate": {"value": brief_open_rate},
                "inaccurate_reason_report_rate": {"value": inaccurate_reason_report_rate},
            },
        }


if __name__ == "__main__":
    unittest.main()
