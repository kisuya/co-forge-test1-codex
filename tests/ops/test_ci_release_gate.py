from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CiReleaseGateTests(unittest.TestCase):
    def test_workflow_wires_api_web_e2e_and_release_checklist_gates(self) -> None:
        workflow_path = Path(".github/workflows/ci-release-gate.yml")
        self.assertTrue(workflow_path.exists())
        content = workflow_path.read_text(encoding="utf-8")

        self.assertIn("api-worker-tests:", content)
        self.assertIn("web-tests:", content)
        self.assertIn("e2e-tests:", content)
        self.assertIn("release-checklist-gate:", content)
        self.assertIn("./.forge/scripts/test_fast.sh", content)
        self.assertIn("pnpm --dir apps/web test", content)
        self.assertIn("python3 scripts/validate_release_checklist.py", content)

    def test_release_checklist_validator_blocks_incomplete_items(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-checklist-") as tmpdir:
            checklist_path = Path(tmpdir) / "checklist.json"
            checklist_path.write_text(
                json.dumps(
                    {
                        "version_tag": "v1.2.3",
                        "release_approved_by": "qa-owner",
                        "release_approved_at_utc": "2026-02-17T00:00:00Z",
                        "release_approval_log": "docs/release/approval-log-v1.2.3.md",
                        "checks": {
                            "api_tests_passed": True,
                            "web_tests_passed": True,
                            "worker_tests_passed": True,
                            "e2e_tests_passed": False,
                            "perf_security_smoke_passed": True,
                            "migration_reviewed": True,
                            "rollback_plan_verified": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_release_checklist.py",
                    str(checklist_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checks.e2e_tests_passed", result.stdout)

    def test_release_checklist_validator_accepts_project_checklist(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/validate_release_checklist.py",
                "docs/release/beta-release-checklist.json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("validation passed", result.stdout.lower())

    def test_release_doc_includes_tagging_and_approval_log_procedure(self) -> None:
        doc_path = Path("docs/release/beta-release-checklist.md")
        self.assertTrue(doc_path.exists())
        content = doc_path.read_text(encoding="utf-8")

        self.assertIn("Version Tagging Procedure", content)
        self.assertIn("vX.Y.Z", content)
        self.assertIn("Release Approval Log", content)


if __name__ == "__main__":
    unittest.main()
