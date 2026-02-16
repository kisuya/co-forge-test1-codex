from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class PushTokenApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="push-token-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/push.sqlite"
        os.environ["JWT_SECRET"] = "push-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-push-token-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

        self.user_a = self.client.post(
            "/v1/auth/signup",
            json={"email": "push-a@example.com", "password": "push-password-a"},
        ).json()
        self.user_b = self.client.post(
            "/v1/auth/signup",
            json={"email": "push-b@example.com", "password": "push-password-b"},
        ).json()

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_duplicate_registration_is_idempotent(self) -> None:
        first = self.client.post(
            "/v1/push-tokens",
            json={"token": "device-token-1", "platform": "iOS"},
            headers=self._auth(self.user_a["access_token"]),
        )
        second = self.client.post(
            "/v1/push-tokens",
            json={"token": "device-token-1", "platform": "ios"},
            headers=self._auth(self.user_a["access_token"]),
        )
        listing = self.client.get(
            "/v1/push-tokens",
            headers=self._auth(self.user_a["access_token"]),
        )

        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["created"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(first.json()["push_token"]["id"], second.json()["push_token"]["id"])

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 1)
        self.assertEqual(listing.json()["items"][0]["platform"], "ios")

    def test_invalid_platform_returns_400(self) -> None:
        response = self.client.post(
            "/v1/push-tokens",
            json={"token": "device-token-2", "platform": "web"},
            headers=self._auth(self.user_a["access_token"]),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_input")

    def test_delete_is_user_scoped(self) -> None:
        create = self.client.post(
            "/v1/push-tokens",
            json={"token": "device-token-3", "platform": "android"},
            headers=self._auth(self.user_a["access_token"]),
        )
        self.assertEqual(create.status_code, 201)

        blocked = self.client.delete(
            "/v1/push-tokens?token=device-token-3",
            headers=self._auth(self.user_b["access_token"]),
        )
        owner = self.client.delete(
            "/v1/push-tokens?token=device-token-3",
            headers=self._auth(self.user_a["access_token"]),
        )
        listed = self.client.get(
            "/v1/push-tokens",
            headers=self._auth(self.user_a["access_token"]),
        )

        self.assertEqual(blocked.status_code, 200)
        self.assertFalse(blocked.json()["deleted"])
        self.assertEqual(owner.status_code, 200)
        self.assertTrue(owner.json()["deleted"])
        self.assertEqual(listed.json()["count"], 0)

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
