from __future__ import annotations

from pathlib import Path
import re
import unittest


class DockerComposeServicesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compose_path = Path("docker-compose.yml")
        self.readme_path = Path("README.md")

    def test_compose_defines_required_services(self) -> None:
        self.assertTrue(self.compose_path.exists())
        compose = self.compose_path.read_text(encoding="utf-8")

        for service_name in ("postgres", "redis", "api", "web", "worker"):
            self.assertRegex(compose, rf"(?m)^  {service_name}:$")

    def test_dependency_healthchecks_and_data_volumes_are_configured(self) -> None:
        compose = self.compose_path.read_text(encoding="utf-8")

        for infra_service in ("postgres", "redis"):
            block = self._service_block(compose, infra_service)
            self.assertIn("healthcheck:", block)

        for runtime_service in ("api", "web", "worker"):
            block = self._service_block(compose, runtime_service)
            self.assertIn("depends_on:", block)
            self.assertIn("condition: service_healthy", block)
            self.assertIn("healthcheck:", block)

        self.assertRegex(compose, r"(?m)^volumes:$")
        self.assertRegex(compose, r"(?m)^  postgres_data:$")
        self.assertRegex(compose, r"(?m)^  redis_data:$")

    def test_readme_documents_volume_preserve_and_reset_options(self) -> None:
        self.assertTrue(self.readme_path.exists())
        readme = self.readme_path.read_text(encoding="utf-8")
        self.assertIn("docker compose down", readme)
        self.assertIn("docker compose down -v", readme)

    def _service_block(self, compose: str, service_name: str) -> str:
        pattern = re.compile(
            rf"(?ms)^  {re.escape(service_name)}:\n(?P<block>(?:    .*\n)+?)(?=^  [a-z0-9_-]+:|^volumes:)",
        )
        match = pattern.search(compose)
        self.assertIsNotNone(match, msg=f"service '{service_name}' block not found")
        return match.group("block")


if __name__ == "__main__":
    unittest.main()
