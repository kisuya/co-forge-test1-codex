from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.auth_tokens import issue_access_token
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class AuthGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="auth-guard-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/auth_guard.sqlite"
        os.environ["JWT_SECRET"] = "test-auth-guard-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-auth-guard-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_valid_bearer_token_allows_access_and_injects_user(self) -> None:
        signup = self.client.post(
            "/v1/auth/signup",
            json={"email": "guard@example.com", "password": "guard-password"},
        ).json()
        token = signup["access_token"]

        response = self.client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["user"]["id"], signup["user_id"])
        self.assertEqual(body["user"]["email"], "guard@example.com")

    def test_expired_or_invalid_signature_token_returns_401(self) -> None:
        expired_token = issue_access_token(
            user_id="expired-user",
            email="expired@example.com",
            ttl_seconds=1,
            now_utc=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        expired = self.client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(expired.json()["code"], "invalid_token")

        signup = self.client.post(
            "/v1/auth/signup",
            json={"email": "sign@example.com", "password": "sign-password"},
        ).json()
        token = signup["access_token"]
        tampered_token = f"{token[:-1]}x"
        invalid_signature = self.client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        self.assertEqual(invalid_signature.status_code, 401)
        self.assertEqual(invalid_signature.json()["code"], "invalid_token")

    def test_clock_skew_is_limited_to_30_seconds(self) -> None:
        within_skew_token = issue_access_token(
            user_id="skew-user",
            email="skew@example.com",
            ttl_seconds=1,
            now_utc=datetime.now(timezone.utc) - timedelta(seconds=25),
        )
        within = self.client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {within_skew_token}"},
        )
        self.assertEqual(within.status_code, 200)

        beyond_skew_token = issue_access_token(
            user_id="skew-user",
            email="skew@example.com",
            ttl_seconds=1,
            now_utc=datetime.now(timezone.utc) - timedelta(seconds=35),
        )
        beyond = self.client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {beyond_skew_token}"},
        )
        self.assertEqual(beyond.status_code, 401)
        self.assertEqual(beyond.json()["code"], "invalid_token")

    def test_forbidden_resource_access_returns_403(self) -> None:
        first = self.client.post(
            "/v1/auth/signup",
            json={"email": "first@example.com", "password": "first-password"},
        ).json()
        second = self.client.post(
            "/v1/auth/signup",
            json={"email": "second@example.com", "password": "second-password"},
        ).json()

        response = self.client.get(
            f"/v1/auth/users/{second['user_id']}",
            headers={"Authorization": f"Bearer {first['access_token']}"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(body["code"], "forbidden")
        self.assertIn("request_id", body)


if __name__ == "__main__":
    unittest.main()
