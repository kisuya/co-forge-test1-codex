from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from apps.ops.project_state_consistency_guard import generate_project_state_consistency_report


class ProjectStateConsistencyGuardTests(unittest.TestCase):
    def test_generate_report_passes_when_counts_and_done_ids_match(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-state-pass-") as tmpdir:
            features_path = Path(tmpdir) / "features.json"
            progress_path = Path(tmpdir) / "progress.txt"
            output_path = Path(tmpdir) / "report.json"

            self._write_features(
                features_path,
                [
                    {"id": "watch-001", "status": "done"},
                    {"id": "watch-002", "status": "pending"},
                    {"id": "watch-003", "status": "blocked"},
                ],
            )
            self._write_progress(
                progress_path,
                """
Session: 1
Progress: 1/3 done (1 pending, 1 blocked)
<!-- done: watch-001 -->
""".strip(),
            )

            report = generate_project_state_consistency_report(
                features_path=features_path,
                progress_path=progress_path,
                output_path=output_path,
                generated_at_utc="2026-02-17T12:00:00Z",
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["mismatch_count"], 0)
            self.assertEqual(report["warning_count"], 0)
            self.assertTrue(output_path.exists())

    def test_generate_report_fails_on_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-state-count-mismatch-") as tmpdir:
            features_path = Path(tmpdir) / "features.json"
            progress_path = Path(tmpdir) / "progress.txt"
            output_path = Path(tmpdir) / "report.json"

            self._write_features(
                features_path,
                [
                    {"id": "watch-001", "status": "done"},
                    {"id": "watch-002", "status": "pending"},
                ],
            )
            self._write_progress(
                progress_path,
                """
Session: 1
Progress: 0/2 done (2 pending, 0 blocked)
<!-- done: watch-001 -->
""".strip(),
            )

            report = generate_project_state_consistency_report(
                features_path=features_path,
                progress_path=progress_path,
                output_path=output_path,
            )

            self.assertEqual(report["status"], "fail")
            codes = {item["code"] for item in report["mismatches"]}
            self.assertIn("progress_counts_mismatch", codes)

    def test_generate_report_fails_on_done_list_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-state-done-mismatch-") as tmpdir:
            features_path = Path(tmpdir) / "features.json"
            progress_path = Path(tmpdir) / "progress.txt"
            output_path = Path(tmpdir) / "report.json"

            self._write_features(
                features_path,
                [
                    {"id": "watch-001", "status": "done"},
                    {"id": "watch-002", "status": "done"},
                    {"id": "watch-003", "status": "pending"},
                ],
            )
            self._write_progress(
                progress_path,
                """
Session: 1
Progress: 2/3 done (1 pending, 0 blocked)
<!-- done: watch-001, ghost-feature -->
""".strip(),
            )

            report = generate_project_state_consistency_report(
                features_path=features_path,
                progress_path=progress_path,
                output_path=output_path,
            )

            self.assertEqual(report["status"], "fail")
            mismatch = next(item for item in report["mismatches"] if item["code"] == "done_id_set_mismatch")
            self.assertIn("missing=watch-002", mismatch["message"])
            self.assertIn("extra=ghost-feature", mismatch["message"])

    def test_generate_report_fails_on_duplicate_feature_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-state-duplicate-feature-") as tmpdir:
            features_path = Path(tmpdir) / "features.json"
            progress_path = Path(tmpdir) / "progress.txt"
            output_path = Path(tmpdir) / "report.json"

            self._write_features(
                features_path,
                [
                    {"id": "watch-001", "status": "done"},
                    {"id": "watch-001", "status": "pending"},
                ],
            )
            self._write_progress(
                progress_path,
                """
Session: 1
Progress: 1/2 done (1 pending, 0 blocked)
<!-- done: watch-001 -->
""".strip(),
            )

            report = generate_project_state_consistency_report(
                features_path=features_path,
                progress_path=progress_path,
                output_path=output_path,
            )

            self.assertEqual(report["status"], "fail")
            codes = {item["code"] for item in report["mismatches"]}
            self.assertIn("duplicate_feature_id", codes)

    def test_cli_allows_summary_pending_when_flag_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-state-cli-") as tmpdir:
            features_path = Path(tmpdir) / "features.json"
            progress_path = Path(tmpdir) / "progress.txt"
            output_path = Path(tmpdir) / "report.json"

            self._write_features(
                features_path,
                [
                    {"id": "ops-003", "status": "done"},
                    {"id": "ops-004", "status": "done"},
                ],
            )
            self._write_progress(
                progress_path,
                """
Session: 23
Progress: 1/2 done (1 pending, 0 blocked)
<!-- done: ops-003 -->
Summary: ops-004 구현 완료
""".strip(),
            )

            strict_proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/project_state_consistency_guard.py",
                    "--features",
                    str(features_path),
                    "--progress",
                    str(progress_path),
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(strict_proc.returncode, 1)
            self.assertIn("project_state=fail", strict_proc.stdout)

            relaxed_proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/project_state_consistency_guard.py",
                    "--features",
                    str(features_path),
                    "--progress",
                    str(progress_path),
                    "--output",
                    str(output_path),
                    "--allow-summary-pending",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(relaxed_proc.returncode, 0)
            self.assertIn("project_state=pass", relaxed_proc.stdout)
            self.assertIn("warning[pending_checkpoint_summary]", relaxed_proc.stdout)

    def _write_features(self, path: Path, features: list[dict[str, object]]) -> None:
        payload = {
            "project": "project-test",
            "goal": "goal",
            "agent": "codex",
            "features": features,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_progress(self, path: Path, content: str) -> None:
        path.write_text(content + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
