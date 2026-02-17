from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.briefs import (
    BriefExpiredError,
    BriefNotFoundError,
    brief_inbox_store,
)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 50


def register_brief_routes(app: FastAPI) -> None:
    @app.get("/v1/briefs")
    def list_briefs(request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        size = _parse_size(request.query_params.get("size"))

        records = brief_inbox_store.list_briefs(user_id=user.user_id, limit=size)
        unread_count = brief_inbox_store.count_unread(user_id=user.user_id)
        pre_market_count = sum(1 for record in records if record.brief_type == "pre_market")
        post_close_count = sum(1 for record in records if record.brief_type == "post_close")

        return {
            "items": [brief_inbox_store.to_summary_dict(record) for record in records],
            "count": len(records),
            "meta": {
                "unread_count": unread_count,
                "pre_market_count": pre_market_count,
                "post_close_count": post_close_count,
            },
        }

    @app.get("/v1/briefs/{brief_id}")
    def get_brief_detail(brief_id: str, request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        try:
            record = brief_inbox_store.get_brief(user_id=user.user_id, brief_id=brief_id)
        except BriefExpiredError as exc:
            raise HTTPException(
                status_code=410,
                code="brief_link_expired",
                message="Brief link has expired",
                details={"brief_id": brief_id, "retryable": False},
            ) from exc
        except BriefNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                code="brief_not_found",
                message="Brief not found",
                details={"brief_id": brief_id},
            ) from exc

        return {"brief": brief_inbox_store.to_detail_dict(record)}

    @app.patch("/v1/briefs/{brief_id}/read")
    def mark_brief_read(brief_id: str, request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        try:
            record = brief_inbox_store.mark_read(user_id=user.user_id, brief_id=brief_id)
        except BriefNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                code="brief_not_found",
                message="Brief not found",
                details={"brief_id": brief_id},
            ) from exc

        return {
            "brief": brief_inbox_store.to_summary_dict(record),
            "unread_count": brief_inbox_store.count_unread(user_id=user.user_id),
        }



def _parse_size(raw: str | None) -> int:
    text = (raw or str(_DEFAULT_PAGE_SIZE)).strip()
    try:
        size = int(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="size must be an integer",
            details={"size": text},
        ) from exc

    if size < 1 or size > _MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message=f"size must be between 1 and {_MAX_PAGE_SIZE}",
            details={"size": size},
        )
    return size
