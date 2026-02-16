from __future__ import annotations

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

REQUIRED_ENV_VARS = (
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET",
    "SEC_USER_AGENT",
    "DART_API_KEY",
    "MARKET_DATA_API_KEY",
)


class BootstrapScriptsTests(unittest.TestCase):
    def test_env_example_contains_required_keys(self) -> None:
        content = Path(".env.example").read_text(encoding="utf-8")
        for name in REQUIRED_ENV_VARS:
            self.assertIn(f"{name}=", content)

    def test_missing_env_vars_are_reported_per_item(self) -> None:
        output = self._run_script("scripts/bootstrap_install.sh", env={"PATH": os.environ.get("PATH", "")})
        self.assertNotEqual(output.returncode, 0)
        combined = output.stdout + output.stderr

        for name in REQUIRED_ENV_VARS:
            self.assertIn(f"missing env var: {name}", combined)

        self.assertIn("step=validate_env status=failed", combined)

    def test_bootstrap_scripts_emit_step_logs_on_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-scripts-") as tmpdir:
            env = {
                "PATH": os.environ.get("PATH", ""),
                "DATABASE_URL": f"sqlite:///{tmpdir}/bootstrap.sqlite",
                "REDIS_URL": "redis://localhost:6379/0",
                "JWT_SECRET": "bootstrap-secret",
                "SEC_USER_AGENT": "test-agent/1.0",
                "DART_API_KEY": "dart-key",
                "MARKET_DATA_API_KEY": "market-key",
            }

            install = self._run_script("scripts/bootstrap_install.sh", env=env)
            self.assertEqual(install.returncode, 0)
            self.assertIn("step=validate_env status=ok", install.stdout)
            self.assertIn("step=completed status=ok", install.stdout)

            migrate = self._run_script("scripts/bootstrap_migrate.sh", env=env)
            self.assertEqual(migrate.returncode, 0)
            self.assertIn("step=run_migrations status=ok", migrate.stdout)
            self.assertIn("step=completed status=ok", migrate.stdout)

            health = self._run_script("scripts/bootstrap_health.sh", env=env)
            self.assertEqual(health.returncode, 0)
            self.assertIn("step=database_health status=ok", health.stdout)
            self.assertIn("step=redis_health status=skipped", health.stdout)
            self.assertIn("step=completed status=ok", health.stdout)

    def _run_script(self, path: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", path],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
