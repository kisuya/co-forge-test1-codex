from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.push_tokens_db import push_tokens_db_service


def register_push_token_routes(app: FastAPI) -> None:
    @app.post("/v1/push-tokens")
    def register_push_token(request: Request, body: dict[str, object]) -> tuple[dict[str, object], int]:
        user = require_authenticated_user(request)
        token = str(body.get("token", ""))
        platform = str(body.get("platform", ""))
        try:
            record, created = push_tokens_db_service.upsert_token(
                user_id=user.user_id,
                token=token,
                platform=platform,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid push token payload",
                details={"error": str(exc)},
            ) from exc
        status_code = 201 if created else 200
        return {"push_token": record.to_dict(), "created": created}, status_code

    @app.get("/v1/push-tokens")
    def list_push_tokens(request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        records = push_tokens_db_service.list_tokens(user_id=user.user_id)
        return {"items": [record.to_dict() for record in records], "count": len(records)}

    @app.delete("/v1/push-tokens/{token}")
    @app.delete("/v1/push-tokens")
    def unregister_push_token(request: Request, token: str | None = None) -> dict[str, object]:
        user = require_authenticated_user(request)
        source_token = token if token is not None else str(request.query_params.get("token", ""))
        try:
            deleted = push_tokens_db_service.delete_token(user_id=user.user_id, token=source_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid push token payload",
                details={"error": str(exc)},
            ) from exc
        return {"deleted": deleted}
