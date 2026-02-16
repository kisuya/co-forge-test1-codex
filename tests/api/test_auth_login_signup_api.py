from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.passwords import verify_password
from apps.infra.models import create_core_schema, drop_core_schema, fetch_all
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class AuthLoginSignupApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="auth-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/auth.sqlite"
        os.environ["JWT_SECRET"] = "test-jwt-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-auth-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_signup_creates_user_with_bcrypt_hash_and_returns_token(self) -> None:
        response = self.client.post(
            "/v1/auth/signup",
            json={"email": "Trader@Example.com", "password": "safe-password-123"},
            headers={"X-Request-ID": "req-auth-signup"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.headers.get("x-request-id"), "req-auth-signup")
        self.assertIn("user_id", body)
        self.assertEqual(body["access_token"].count("."), 2)

        rows = fetch_all(
            self.runtime.engine,
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            ("trader@example.com",),
        )
        self.assertEqual(len(rows), 1)

        user_id, email, stored_hash = rows[0]
        self.assertEqual(body["user_id"], user_id)
        self.assertEqual(email, "trader@example.com")
        self.assertNotEqual(stored_hash, "safe-password-123")
        self.assertTrue(str(stored_hash).startswith("$2"))
        self.assertTrue(verify_password("safe-password-123", str(stored_hash)))

    def test_duplicate_email_returns_409(self) -> None:
        first = self.client.post(
            "/v1/auth/signup",
            json={"email": "dup@example.com", "password": "first-password"},
        )
        second = self.client.post(
            "/v1/auth/signup",
            json={"email": "DUP@EXAMPLE.COM", "password": "second-password"},
        )
        body = second.json()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(body["code"], "email_already_exists")
        self.assertIn("request_id", body)
        self.assertIn("details", body)

    def test_login_success_and_invalid_credentials(self) -> None:
        signup = self.client.post(
            "/v1/auth/signup",
            json={"email": "login@example.com", "password": "correct-password"},
        ).json()

        success = self.client.post(
            "/v1/auth/login",
            json={"email": "LOGIN@example.com", "password": "correct-password"},
        )
        success_body = success.json()
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success_body["user_id"], signup["user_id"])
        self.assertEqual(success_body["access_token"].count("."), 2)

        invalid = self.client.post(
            "/v1/auth/login",
            json={"email": "login@example.com", "password": "wrong-password"},
        )
        invalid_body = invalid.json()
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid_body["code"], "invalid_credentials")
        self.assertIn("request_id", invalid_body)

    def test_invalid_payload_returns_400(self) -> None:
        response = self.client.post(
            "/v1/auth/signup",
            json={"email": "invalid-email", "password": "short"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "invalid_input")
        self.assertIn("request_id", body)
        self.assertIn("details", body)


if __name__ == "__main__":
    unittest.main()
