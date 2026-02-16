from __future__ import annotations

import asyncio
import inspect
import re
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit


def _normalize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {key.lower(): value for key, value in headers.items()}


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    if not path.startswith("/"):
        return f"/{path}"
    return path


def _status_to_code(status_code: int) -> str:
    default_map = {
        404: "not_found",
        405: "method_not_allowed",
        422: "validation_error",
        500: "internal_error",
    }
    return default_map.get(status_code, "http_error")


class HTTPException(Exception):
    def __init__(
        self,
        status_code: int,
        message: str | None = None,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str]
    query_params: dict[str, str]
    path_params: dict[str, str] = field(default_factory=dict)
    body: Any = None
    request_id: str = ""

    def json(self) -> Any:
        return self.body


class Response:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = _normalize_headers(headers)

    def json(self) -> Any:
        return self._payload


@dataclass
class _Route:
    method: str
    path: str
    pattern: re.Pattern[str]
    endpoint: Callable[..., Any]


class FastAPI:
    def __init__(self, title: str | None = None) -> None:
        self.title = title or "FastAPI"
        self._routes: list[_Route] = []
        self._exception_handlers: dict[type[Exception], Callable[..., Any]] = {}

    def add_api_route(
        self, path: str, endpoint: Callable[..., Any], methods: list[str]
    ) -> None:
        normalized_path = _normalize_path(path)
        regex = self._compile_path_regex(normalized_path)
        for method in methods:
            self._routes.append(
                _Route(
                    method=method.upper(),
                    path=normalized_path,
                    pattern=regex,
                    endpoint=endpoint,
                )
            )

    def get(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._method_decorator(path, "GET")

    def post(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._method_decorator(path, "POST")

    def patch(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._method_decorator(path, "PATCH")

    def delete(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._method_decorator(path, "DELETE")

    def exception_handler(
        self, exc_type: type[Exception]
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._exception_handlers[exc_type] = func
            return func

        return decorator

    def add_exception_handler(
        self, exc_type: type[Exception], func: Callable[..., Any]
    ) -> None:
        self._exception_handlers[exc_type] = func

    def handle_request(
        self,
        method: str,
        url: str,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        normalized_headers = _normalize_headers(headers)
        request_id = normalized_headers.get("x-request-id", str(uuid.uuid4()))
        request = self._build_request(method, url, json_body, normalized_headers, request_id)

        try:
            route, path_params = self._match_route(request.method, request.path)
            request.path_params = path_params
            payload = self._invoke_endpoint(route.endpoint, request)
            response = self._coerce_response(payload)
        except Exception as exc:  # noqa: BLE001
            response = self._handle_exception(exc, request_id)

        response.headers.setdefault("x-request-id", request_id)
        return response

    def _method_decorator(
        self, path: str, method: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.add_api_route(path, func, [method])
            return func

        return decorator

    def _compile_path_regex(self, path: str) -> re.Pattern[str]:
        if path == "/":
            return re.compile(r"^/$")
        stripped = path.rstrip("/")
        converted = re.sub(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", r"(?P<\1>[^/]+)", stripped)
        return re.compile(f"^{converted}/?$")

    def _build_request(
        self,
        method: str,
        url: str,
        json_body: Any,
        headers: dict[str, str],
        request_id: str,
    ) -> Request:
        parsed = urlsplit(url)
        path = _normalize_path(parsed.path or "/")
        query_params = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        return Request(
            method=method.upper(),
            path=path,
            headers=headers,
            query_params=query_params,
            body=json_body,
            request_id=request_id,
        )

    def _match_route(self, method: str, path: str) -> tuple[_Route, dict[str, str]]:
        path_matches = [route for route in self._routes if route.pattern.match(path)]
        if not path_matches:
            raise HTTPException(
                status_code=404,
                code="not_found",
                message="Not found",
                details={"path": path},
            )

        for route in path_matches:
            if route.method == method:
                match = route.pattern.match(path)
                return route, match.groupdict() if match else {}

        allowed = sorted({route.method for route in path_matches})
        raise HTTPException(
            status_code=405,
            code="method_not_allowed",
            message="Method not allowed",
            details={"method": method, "allowed_methods": allowed},
        )

    def _invoke_endpoint(self, endpoint: Callable[..., Any], request: Request) -> Any:
        signature = inspect.signature(endpoint)
        kwargs: dict[str, Any] = {}

        for name, param in signature.parameters.items():
            if name == "request":
                kwargs[name] = request
                continue
            if name in request.path_params:
                kwargs[name] = request.path_params[name]
                continue
            if name == "body":
                kwargs[name] = request.body
                continue
            if isinstance(request.body, dict) and name in request.body:
                kwargs[name] = request.body[name]
                continue
            if param.default is inspect.Parameter.empty:
                raise HTTPException(
                    status_code=422,
                    code="validation_error",
                    message="Missing required parameter",
                    details={"parameter": name},
                )

        result = endpoint(**kwargs)
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result

    def _coerce_response(self, payload: Any) -> Response:
        if isinstance(payload, Response):
            return payload

        status_code = 200
        body = payload
        if isinstance(payload, tuple) and len(payload) == 2:
            first, second = payload
            if isinstance(first, int) and not isinstance(second, int):
                status_code, body = first, second
            else:
                body, status_code = first, int(second)

        return Response(status_code=status_code, payload=body)

    def _handle_exception(self, exc: Exception, request_id: str) -> Response:
        for exc_type, handler in self._exception_handlers.items():
            if isinstance(exc, exc_type):
                handler_result = handler(exc, request_id)
                response = self._coerce_response(handler_result)
                if "request_id" not in response.json():
                    payload = response.json()
                    if isinstance(payload, dict):
                        payload["request_id"] = request_id
                return response

        if isinstance(exc, HTTPException):
            return self._http_exception_response(exc, request_id)
        return self._internal_exception_response(request_id)

    def _http_exception_response(self, exc: HTTPException, request_id: str) -> Response:
        status_phrase = HTTPStatus(exc.status_code).phrase if exc.status_code in HTTPStatus._value2member_map_ else "HTTP Error"
        payload = {
            "code": exc.code or _status_to_code(exc.status_code),
            "message": exc.message or status_phrase,
            "details": exc.details,
            "request_id": request_id,
        }
        return Response(status_code=exc.status_code, payload=payload)

    def _internal_exception_response(self, request_id: str) -> Response:
        payload = {
            "code": "internal_error",
            "message": "Internal server error",
            "details": None,
            "request_id": request_id,
        }
        return Response(status_code=500, payload=payload)


__all__ = ["FastAPI", "HTTPException", "Request", "Response"]
