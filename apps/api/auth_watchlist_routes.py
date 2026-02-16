from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import enforce_user_scope, require_authenticated_user
from apps.domain.auth import (
    AuthInputError,
    DuplicateEmailError,
    InvalidCredentialsError,
    auth_service,
)
from apps.domain.watchlists import watchlist_service
from apps.domain.watchlists_db import watchlist_db_service
from apps.infra.observability import log_error, log_info, request_context

_DEFAULT_PAGE = 1
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


def register_auth_watchlist_routes(app: FastAPI) -> None:
    @app.post("/v1/auth/signup")
    def signup(request: Request, body: dict[str, str]) -> tuple[dict[str, str], int]:
        with request_context(request.request_id):
            email = body.get("email", "")
            password = body.get("password", "")
            log_info(
                feature="auth-001",
                event="auth_signup_requested",
                request_id=request.request_id,
                logger_name="oh_my_stock.api",
                email=email,
                password=password,
            )
            try:
                result = auth_service.signup(email=email, password=password)
            except AuthInputError as exc:
                log_error(
                    feature="auth-001",
                    event="auth_signup_failed",
                    request_id=request.request_id,
                    logger_name="oh_my_stock.api",
                    email=email,
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=400,
                    code="invalid_input",
                    message="Invalid auth payload",
                    details={"error": str(exc)},
                ) from exc
            except DuplicateEmailError as exc:
                log_error(
                    feature="auth-001",
                    event="auth_signup_failed",
                    request_id=request.request_id,
                    logger_name="oh_my_stock.api",
                    email=email,
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=409,
                    code="email_already_exists",
                    message="Email already exists",
                    details={"email": body.get("email", "").strip().lower(), "error": str(exc)},
                ) from exc

            log_info(
                feature="auth-001",
                event="auth_signup_succeeded",
                request_id=request.request_id,
                logger_name="oh_my_stock.api",
                user_id=result.user_id,
                email=email,
                access_token=result.access_token,
            )
            return {"user_id": result.user_id, "access_token": result.access_token}, 201

    @app.post("/v1/auth/login")
    def login(request: Request, body: dict[str, str]) -> dict[str, str]:
        with request_context(request.request_id):
            email = body.get("email", "")
            password = body.get("password", "")
            log_info(
                feature="auth-001",
                event="auth_login_requested",
                request_id=request.request_id,
                logger_name="oh_my_stock.api",
                email=email,
                password=password,
            )
            try:
                result = auth_service.login(email=email, password=password)
            except AuthInputError as exc:
                log_error(
                    feature="auth-001",
                    event="auth_login_failed",
                    request_id=request.request_id,
                    logger_name="oh_my_stock.api",
                    email=email,
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=400,
                    code="invalid_input",
                    message="Invalid auth payload",
                    details={"error": str(exc)},
                ) from exc
            except InvalidCredentialsError as exc:
                log_error(
                    feature="auth-001",
                    event="auth_login_failed",
                    request_id=request.request_id,
                    logger_name="oh_my_stock.api",
                    email=email,
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=401,
                    code="invalid_credentials",
                    message="Invalid email or password",
                    details={"error": str(exc)},
                ) from exc

            log_info(
                feature="auth-001",
                event="auth_login_succeeded",
                request_id=request.request_id,
                logger_name="oh_my_stock.api",
                user_id=result.user_id,
                email=email,
                access_token=result.access_token,
            )
            return {"user_id": result.user_id, "access_token": result.access_token}

    @app.get("/v1/auth/me")
    def get_authenticated_me(request: Request) -> dict[str, object]:
        with request_context(request.request_id):
            user = require_authenticated_user(request)
        log_info(
            feature="auth-002",
            event="auth_me_succeeded",
            request_id=request.request_id,
            logger_name="oh_my_stock.api",
            user_id=user.user_id,
        )
        return {"user": {"id": user.user_id, "email": user.email}}

    @app.get("/v1/auth/users/{user_id}")
    def get_user_scoped_resource(user_id: str, request: Request) -> dict[str, object]:
        with request_context(request.request_id):
            user = require_authenticated_user(request)
            enforce_user_scope(user, requested_user_id=user_id)
        log_info(
            feature="auth-002",
            event="auth_scope_check_succeeded",
            request_id=request.request_id,
            logger_name="oh_my_stock.api",
            user_id=user.user_id,
            requested_user_id=user_id,
        )
        return {"authorized": True, "user_id": user.user_id}

    @app.post("/v1/watchlists/items")
    def create_watchlist_item(request: Request, body: dict[str, str]) -> tuple[dict[str, object], int]:
        authorization = request.headers.get("authorization", "").strip()
        if not authorization:
            try:
                item, is_duplicate = watchlist_service.create_item(
                    symbol=body.get("symbol", ""),
                    market=body.get("market", ""),
                    user_id=body.get("user_id"),
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    code="invalid_input",
                    message="Invalid watchlist item payload",
                    details={"error": str(exc)},
                ) from exc

            status_code = 200 if is_duplicate else 201
            return {"item": item.to_dict(), "is_duplicate": is_duplicate}, status_code

        user = require_authenticated_user(request)
        try:
            item, is_duplicate = watchlist_db_service.create_item(
                symbol=body.get("symbol", ""),
                market=body.get("market", ""),
                user_id=user.user_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid watchlist item payload",
                details={"error": str(exc)},
            ) from exc

        status_code = 200 if is_duplicate else 201
        return {"item": item.to_dict(), "is_duplicate": is_duplicate}, status_code

    @app.get("/v1/watchlists/items")
    def list_watchlist_items(request: Request) -> dict[str, object]:
        page, size = _parse_pagination(request)
        authorization = request.headers.get("authorization", "").strip()

        if not authorization:
            user_id = (request.query_params.get("user_id") or "").strip() or "demo-user"
            source_items = watchlist_service.list_items(user_id=user_id)
            total = len(source_items)
            start = (page - 1) * size
            paginated = source_items[start : start + size]
            items = [item.to_dict() for item in paginated]
        else:
            user = require_authenticated_user(request)
            records, total = watchlist_db_service.list_items(user_id=user.user_id, page=page, size=size)
            items = [record.to_dict() for record in records]

        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
        }

    @app.delete("/v1/watchlists/items/{item_id}")
    def delete_watchlist_item(item_id: str, request: Request) -> dict[str, object]:
        authorization = request.headers.get("authorization", "").strip()
        if not authorization:
            deleted = watchlist_service.delete_item(item_id)
        else:
            user = require_authenticated_user(request)
            deleted = watchlist_db_service.delete_item(item_id=item_id, user_id=user.user_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                code="watchlist_item_not_found",
                message="Watchlist item not found",
                details={"item_id": item_id},
            )
        return {"deleted": True, "item_id": item_id}


def _parse_pagination(request: Request) -> tuple[int, int]:
    page_text = request.query_params.get("page", str(_DEFAULT_PAGE))
    size_text = request.query_params.get("size", str(_DEFAULT_PAGE_SIZE))
    try:
        page = int(page_text)
        size = int(size_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="page and size must be integers",
            details={"page": page_text, "size": size_text},
        ) from exc

    if page < 1:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="page must be >= 1",
            details={"page": page},
        )
    if size < 1 or size > _MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message=f"size must be between 1 and {_MAX_PAGE_SIZE}",
            details={"size": size},
        )
    return page, size
