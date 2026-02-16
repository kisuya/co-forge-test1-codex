from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Response


class TestClient:
    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def request(
        self,
        method: str,
        url: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        return self._app.handle_request(
            method=method,
            url=url,
            json_body=json,
            headers=headers,
        )

    def get(self, url: str, headers: dict[str, str] | None = None) -> Response:
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        return self.request("POST", url, json=json, headers=headers)

    def delete(self, url: str, headers: dict[str, str] | None = None) -> Response:
        return self.request("DELETE", url, headers=headers)
