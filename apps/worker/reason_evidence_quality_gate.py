from __future__ import annotations

from collections.abc import Callable
import os
import socket
from typing import Any
from urllib.parse import urlsplit

_DEFAULT_ALLOWED_DOMAINS = frozenset(
    {
        "community.example",
        "dart.example",
        "example.com",
        "news.example",
        "sec.example",
    }
)
_DEFAULT_RETRY_AFTER_SECONDS = 300


def apply_reason_evidence_quality_gate(
    *,
    candidates: list[dict[str, Any]],
    allowed_domains: set[str] | None = None,
    link_checker: Callable[[str], bool] | None = None,
) -> dict[str, object]:
    effective_domains = _resolve_allowed_domains(allowed_domains)
    accepted_candidates: list[dict[str, Any]] = []
    excluded_candidates: list[dict[str, object]] = []

    for candidate in candidates:
        source_url = str(candidate.get("source_url", "")).strip()
        if not source_url:
            excluded_candidates.append(
                _build_exclusion(candidate=candidate, source_url=source_url, reason="missing_source_url", retryable=False)
            )
            continue

        parsed = urlsplit(source_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            excluded_candidates.append(
                _build_exclusion(candidate=candidate, source_url=source_url, reason="invalid_scheme", retryable=False)
            )
            continue

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            excluded_candidates.append(
                _build_exclusion(candidate=candidate, source_url=source_url, reason="missing_host", retryable=False)
            )
            continue
        if not _is_domain_allowed(hostname=hostname, allowed_domains=effective_domains):
            excluded_candidates.append(
                _build_exclusion(candidate=candidate, source_url=source_url, reason="domain_not_allowed", retryable=False)
            )
            continue

        is_active, reason, retryable = _check_link_activity(source_url=source_url, link_checker=link_checker)
        if not is_active:
            excluded_candidates.append(
                _build_exclusion(
                    candidate=candidate,
                    source_url=source_url,
                    reason=reason,
                    retryable=retryable,
                )
            )
            continue

        accepted_candidates.append(dict(candidate))

    retryable_excluded_count = sum(1 for item in excluded_candidates if bool(item["retryable"]))
    reason_status = "verified" if accepted_candidates else "collecting_evidence"
    retry_after_seconds = _DEFAULT_RETRY_AFTER_SECONDS if retryable_excluded_count > 0 else None
    return {
        "accepted_candidates": accepted_candidates,
        "excluded_candidates": excluded_candidates,
        "reason_status": reason_status,
        "retryable_excluded_count": retryable_excluded_count,
        "retry_after_seconds": retry_after_seconds,
    }


def _resolve_allowed_domains(allowed_domains: set[str] | None) -> set[str]:
    if allowed_domains is not None:
        return {domain.strip().lower() for domain in allowed_domains if domain.strip()}

    raw_domains = os.getenv("REASON_ALLOWED_SOURCE_DOMAINS", "").strip()
    if not raw_domains:
        return set(_DEFAULT_ALLOWED_DOMAINS)

    resolved = {domain.strip().lower() for domain in raw_domains.split(",") if domain.strip()}
    if resolved:
        return resolved
    return set(_DEFAULT_ALLOWED_DOMAINS)


def _is_domain_allowed(*, hostname: str, allowed_domains: set[str]) -> bool:
    for allowed_domain in allowed_domains:
        if hostname == allowed_domain:
            return True
        if hostname.endswith(f".{allowed_domain}"):
            return True
    return False


def _check_link_activity(
    *,
    source_url: str,
    link_checker: Callable[[str], bool] | None,
) -> tuple[bool, str, bool]:
    if link_checker is None:
        return True, "", False

    try:
        is_active = bool(link_checker(source_url))
    except Exception as exc:  # noqa: BLE001 - quality gate standardizes upstream probe failures.
        reason, retryable = _normalize_link_check_error(exc)
        return False, reason, retryable
    if not is_active:
        return False, "inactive_link", False
    return True, "", False


def _normalize_link_check_error(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, TimeoutError):
        return "link_check_timeout", True
    if isinstance(exc, socket.gaierror):
        return "link_unresolvable", True

    message = str(exc).strip()
    lowered = message.lower()
    if "429" in lowered or "rate limit" in lowered:
        return "link_check_rate_limited", True
    if "timeout" in lowered:
        return "link_check_timeout", True
    if "name or service not known" in lowered or "nodename nor servname provided" in lowered:
        return "link_unresolvable", True
    return "link_check_failed", False


def _build_exclusion(
    *,
    candidate: dict[str, Any],
    source_url: str,
    reason: str,
    retryable: bool,
) -> dict[str, object]:
    return {
        "candidate": dict(candidate),
        "source_url": source_url,
        "reason": reason,
        "retryable": retryable,
        "temporary_excluded": retryable,
    }
