from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from apps.ops.release_gate_utils import normalize_generated_at

PROJECT_STATE_SCHEMA_VERSION = 1
ALLOWED_FEATURE_STATUSES = frozenset({"done", "pending", "blocked"})
_PROGRESS_LINE_PATTERN = re.compile(
    r"^Progress:\s*(\d+)\/(\d+)\s+done\s*\((\d+)\s+pending,\s*(\d+)\s+blocked\)\s*$",
    re.MULTILINE,
)
_DONE_MARKER_PATTERN = re.compile(r"<!--\s*done:\s*(.*?)\s*-->", re.MULTILINE)
_SUMMARY_LINE_PATTERN = re.compile(r"^\s*Summary:\s*.+$", re.MULTILINE)


def build_project_state_consistency_report(
    *,
    features_path: str | Path,
    progress_path: str | Path,
    generated_at_utc: str | None = None,
    allow_summary_pending: bool = False,
) -> dict[str, Any]:
    feature_state = _parse_feature_state(Path(features_path))
    progress_state = _parse_progress_state(Path(progress_path))
    mismatches: list[dict[str, str]] = [*feature_state["issues"], *progress_state["issues"]]
    warnings: list[dict[str, str]] = []

    if feature_state["comparable"] and progress_state["comparable"]:
        feature_counts = feature_state["counts"]
        progress_counts = progress_state["counts"]
        if not _counts_match(feature_counts, progress_counts):
            mismatches.append(
                _issue(
                    "progress_counts_mismatch",
                    "features/progress counts differ "
                    f"(features: done={feature_counts['done']} pending={feature_counts['pending']} blocked={feature_counts['blocked']} total={feature_counts['total']}, "
                    f"progress: done={progress_counts['done']} pending={progress_counts['pending']} blocked={progress_counts['blocked']} total={progress_counts['total']})",
                )
            )

        missing_done_ids, extra_done_ids = _done_id_differences(
            feature_done_ids=feature_state["done_ids"],
            progress_done_ids=progress_state["done_ids"],
        )
        if missing_done_ids or extra_done_ids:
            details: list[str] = []
            if missing_done_ids:
                details.append(f"missing={','.join(missing_done_ids)}")
            if extra_done_ids:
                details.append(f"extra={','.join(extra_done_ids)}")
            mismatches.append(_issue("done_id_set_mismatch", "features/progress done list differs (" + " ".join(details) + ")"))

        if allow_summary_pending:
            deferred = _maybe_defer_pending_session_mismatches(
                mismatches=mismatches,
                feature_counts=feature_counts,
                progress_counts=progress_counts,
                missing_done_ids=missing_done_ids,
                extra_done_ids=extra_done_ids,
                has_pending_summary=bool(progress_state["has_pending_summary"]),
            )
            if deferred:
                mismatches = [
                    mismatch
                    for mismatch in mismatches
                    if mismatch["code"] not in {"progress_counts_mismatch", "done_id_set_mismatch"}
                ]
                warnings.append(
                    _issue(
                        "pending_checkpoint_summary",
                        "summary found after latest done marker; deferred "
                        + ", ".join(mismatch["code"] for mismatch in deferred),
                    )
                )

    status = "fail" if mismatches else "pass"
    return {
        "schema_version": PROJECT_STATE_SCHEMA_VERSION,
        "generated_at_utc": normalize_generated_at(generated_at_utc),
        "status": status,
        "features_path": str(features_path),
        "progress_path": str(progress_path),
        "feature_counts": feature_state["counts"],
        "progress_counts": progress_state["counts"],
        "feature_done_ids": feature_state["done_ids"],
        "progress_done_ids": progress_state["done_ids"],
        "mismatch_count": len(mismatches),
        "warning_count": len(warnings),
        "mismatches": mismatches,
        "warnings": warnings,
        "summary": _build_summary(status=status, mismatches=mismatches, warnings=warnings),
    }


def generate_project_state_consistency_report(
    *,
    features_path: str | Path,
    progress_path: str | Path,
    output_path: str | Path,
    generated_at_utc: str | None = None,
    allow_summary_pending: bool = False,
) -> dict[str, Any]:
    report = build_project_state_consistency_report(
        features_path=features_path,
        progress_path=progress_path,
        generated_at_utc=generated_at_utc,
        allow_summary_pending=allow_summary_pending,
    )
    write_project_state_consistency_report(report=report, output_path=output_path)
    return report


def write_project_state_consistency_report(*, report: Mapping[str, Any], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_feature_state(path: Path) -> dict[str, Any]:
    counts = {"done": 0, "pending": 0, "blocked": 0, "total": 0}
    done_ids: list[str] = []
    issues: list[dict[str, str]] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _state(counts=counts, done_ids=done_ids, issues=[_issue("features_missing", f"features file not found: {path}")])
    except json.JSONDecodeError as exc:
        return _state(
            counts=counts,
            done_ids=done_ids,
            issues=[_issue("features_json_decode_error", f"features JSON decode failed: {exc.msg}")],
        )

    if not isinstance(raw, Mapping):
        return _state(counts=counts, done_ids=done_ids, issues=[_issue("features_format_error", "features.json root must be an object")])
    features = raw.get("features")
    if not isinstance(features, list) or not features:
        return _state(
            counts=counts,
            done_ids=done_ids,
            issues=[_issue("features_format_error", "features.json must include a non-empty features array")],
        )

    seen_ids: set[str] = set()
    for index, item in enumerate(features):
        if not isinstance(item, Mapping):
            issues.append(_issue("features_format_error", f"feature[{index}] must be an object"))
            continue
        feature_id = item.get("id")
        status = item.get("status")
        if not isinstance(feature_id, str) or not feature_id.strip():
            issues.append(_issue("features_format_error", f"feature[{index}] missing valid id"))
            continue
        normalized_id = feature_id.strip()
        if normalized_id in seen_ids:
            issues.append(_issue("duplicate_feature_id", f"duplicate feature id detected: {normalized_id}"))
        else:
            seen_ids.add(normalized_id)

        if not isinstance(status, str) or status not in ALLOWED_FEATURE_STATUSES:
            issues.append(_issue("features_format_error", f"feature {normalized_id} has invalid status; expected one of {sorted(ALLOWED_FEATURE_STATUSES)}"))
            continue
        counts[status] += 1
        if status == "done":
            done_ids.append(normalized_id)

    counts["total"] = len(features)
    return _state(counts=counts, done_ids=done_ids, issues=issues)


def _parse_progress_state(path: Path) -> dict[str, Any]:
    counts = {"done": 0, "pending": 0, "blocked": 0, "total": 0}
    done_ids: list[str] = []
    issues: list[dict[str, str]] = []
    has_pending_summary = False
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _state(counts=counts, done_ids=done_ids, issues=[_issue("progress_missing", f"progress file not found: {path}")])
    if not text.strip():
        return _state(counts=counts, done_ids=done_ids, issues=[_issue("progress_empty", "progress.txt is empty")])

    progress_match = None
    for match in _PROGRESS_LINE_PATTERN.finditer(text):
        progress_match = match
    if progress_match is None:
        issues.append(_issue("progress_format_error", "progress.txt missing line in format: Progress: <done>/<total> done (<pending> pending, <blocked> blocked)"))
    else:
        counts = {
            "done": int(progress_match.group(1)),
            "total": int(progress_match.group(2)),
            "pending": int(progress_match.group(3)),
            "blocked": int(progress_match.group(4)),
        }

    done_marker_match = None
    for match in _DONE_MARKER_PATTERN.finditer(text):
        done_marker_match = match
    if done_marker_match is None:
        issues.append(_issue("progress_format_error", "progress.txt missing done marker: <!-- done: ... -->"))
    else:
        raw_done = done_marker_match.group(1).strip()
        if raw_done and raw_done.lower() != "none":
            done_ids = [token.strip() for token in raw_done.split(",") if token.strip()]
            duplicates = _find_duplicates(done_ids)
            if duplicates:
                issues.append(_issue("progress_done_duplicates", "duplicate ids in progress done marker: " + ",".join(duplicates)))
        has_pending_summary = bool(_SUMMARY_LINE_PATTERN.search(text, pos=done_marker_match.end()))

    return _state(counts=counts, done_ids=done_ids, issues=issues, has_pending_summary=has_pending_summary)


def _counts_match(feature_counts: Mapping[str, int], progress_counts: Mapping[str, int]) -> bool:
    return (
        feature_counts["done"] == progress_counts["done"]
        and feature_counts["pending"] == progress_counts["pending"]
        and feature_counts["blocked"] == progress_counts["blocked"]
        and feature_counts["total"] == progress_counts["total"]
    )


def _done_id_differences(*, feature_done_ids: list[str], progress_done_ids: list[str]) -> tuple[list[str], list[str]]:
    feature_done_set = set(feature_done_ids)
    progress_done_set = set(progress_done_ids)
    return sorted(feature_done_set - progress_done_set), sorted(progress_done_set - feature_done_set)


def _maybe_defer_pending_session_mismatches(
    *,
    mismatches: list[dict[str, str]],
    feature_counts: Mapping[str, int],
    progress_counts: Mapping[str, int],
    missing_done_ids: list[str],
    extra_done_ids: list[str],
    has_pending_summary: bool,
) -> list[dict[str, str]]:
    if not has_pending_summary:
        return []
    deferable = [mismatch for mismatch in mismatches if mismatch["code"] in {"progress_counts_mismatch", "done_id_set_mismatch"}]
    if not deferable or not missing_done_ids or extra_done_ids:
        return []
    if progress_counts["total"] != feature_counts["total"]:
        return []
    if progress_counts["done"] >= feature_counts["done"]:
        return []
    return deferable


def _find_duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _build_summary(*, status: str, mismatches: list[dict[str, str]], warnings: list[dict[str, str]]) -> str:
    if status == "pass":
        return "Project state consistency check passed." if not warnings else "Project state consistency check passed with warnings: " + ", ".join(warning["code"] for warning in warnings)
    return "Project state consistency check failed: " + ", ".join(mismatch["code"] for mismatch in mismatches)


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _state(
    *,
    counts: Mapping[str, int],
    done_ids: list[str],
    issues: list[dict[str, str]],
    has_pending_summary: bool = False,
) -> dict[str, Any]:
    return {
        "counts": dict(counts),
        "done_ids": list(done_ids),
        "issues": list(issues),
        "comparable": not issues,
        "has_pending_summary": has_pending_summary,
    }
