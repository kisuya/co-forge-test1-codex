from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.domain.events import parse_utc_datetime, to_utc_iso

_TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def canonicalize_and_dedupe_reason_candidates(
    *,
    candidates: list[dict[str, Any]],
    published_at_tolerance_seconds: int = 300,
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []

    for candidate in candidates:
        normalized = _normalize_candidate(candidate)
        merged = False
        for existing in deduped:
            if _can_merge(
                existing=existing,
                incoming=normalized,
                published_at_tolerance_seconds=published_at_tolerance_seconds,
            ):
                _merge_candidate(existing=existing, incoming=normalized)
                merged = True
                break
        if merged:
            continue
        deduped.append(normalized)

    return [_strip_internal_fields(candidate) for candidate in deduped]


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(candidate)
    original_source_url = str(candidate.get("source_url", "")).strip()
    canonical_source_url, source_host = _canonicalize_source_url(original_source_url)
    title_key = _normalize_title_key(candidate)
    published_at_value, published_at_key = _normalize_published_at(candidate)

    normalized["source_url"] = canonical_source_url
    normalized["canonical_source_url"] = canonical_source_url
    normalized["source_variants"] = [original_source_url] if original_source_url else []
    normalized["_source_host"] = source_host
    normalized["_title_key"] = title_key
    normalized["_published_at_key"] = published_at_key
    if published_at_value is not None:
        normalized["published_at"] = to_utc_iso(published_at_value)
    return normalized


def _can_merge(
    *,
    existing: dict[str, Any],
    incoming: dict[str, Any],
    published_at_tolerance_seconds: int,
) -> bool:
    existing_url = str(existing.get("canonical_source_url", ""))
    incoming_url = str(incoming.get("canonical_source_url", ""))
    if not existing_url or existing_url != incoming_url:
        return False

    existing_host = str(existing.get("_source_host", ""))
    incoming_host = str(incoming.get("_source_host", ""))
    if not existing_host or existing_host != incoming_host:
        return False

    existing_title = str(existing.get("_title_key", ""))
    incoming_title = str(incoming.get("_title_key", ""))
    if not existing_title or not incoming_title:
        return False
    if existing_title != incoming_title:
        return False

    existing_published = existing.get("_published_at_key")
    incoming_published = incoming.get("_published_at_key")
    if not isinstance(existing_published, datetime) or not isinstance(incoming_published, datetime):
        return False

    delta_seconds = abs((existing_published - incoming_published).total_seconds())
    return delta_seconds <= published_at_tolerance_seconds


def _merge_candidate(*, existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    variants = existing.setdefault("source_variants", [])
    if isinstance(variants, list):
        for source_url in incoming.get("source_variants", []):
            if source_url and source_url not in variants:
                variants.append(source_url)

    existing_published = existing.get("_published_at_key")
    incoming_published = incoming.get("_published_at_key")
    if isinstance(existing_published, datetime) and isinstance(incoming_published, datetime):
        earliest = min(existing_published, incoming_published)
        existing["_published_at_key"] = earliest
        existing["published_at"] = to_utc_iso(earliest)


def _canonicalize_source_url(source_url: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(source_url)
    except Exception:  # noqa: BLE001 - conservative fallback keeps original URL and avoids merge.
        return source_url, ""

    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return source_url, ""

    port_segment = ""
    try:
        port = parsed.port
    except ValueError:
        return source_url, ""
    if port is not None and not _is_default_port(scheme=scheme, port=port):
        port_segment = f":{port}"

    path = _normalize_path(parsed.path)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    filtered_query = [(key, value) for key, value in query_pairs if key.lower() not in _TRACKING_QUERY_PARAMS]
    filtered_query.sort()
    query = urlencode(filtered_query, doseq=True)
    canonical = urlunsplit((scheme, f"{host}{port_segment}", path, query, ""))
    return canonical, host


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    normalized = path
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized or "/"


def _is_default_port(*, scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def _normalize_title_key(candidate: dict[str, Any]) -> str:
    title = str(candidate.get("title") or candidate.get("summary") or "").strip()
    if not title:
        return ""
    return " ".join(title.split()).casefold()


def _normalize_published_at(candidate: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    raw_value = candidate.get("published_at")
    if raw_value is None:
        return None, None
    try:
        published_at = parse_utc_datetime(raw_value)
    except Exception:  # noqa: BLE001 - conservative fallback keeps candidate unmerged.
        return None, None
    return published_at, published_at


def _strip_internal_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(candidate)
    for key in ("_source_host", "_title_key", "_published_at_key"):
        cleaned.pop(key, None)
    return cleaned
