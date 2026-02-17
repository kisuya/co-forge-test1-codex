from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Mapping

from apps.domain.product_kpi import (
    BRIEF_OPEN_RATE,
    CARD_CLICK_RATE,
    EVIDENCE_CLICK_RATE,
    INACCURATE_REASON_REPORT_RATE,
)
from apps.ops.release_gate_policy import ReleaseGatePolicy
from apps.ops.release_gate_utils import (
    build_summary,
    extract_float,
    extract_metric_value,
    extract_str_list,
    normalize_generated_at,
    normalize_status,
)

RELEASE_GATE_SCHEMA_VERSION = 1
REQUIRED_GATES = ("contract", "e2e", "visual_regression", "product_kpi")
DEFAULT_ARTIFACT_FILES = {
    "contract": "contract_smoke.json",
    "e2e": "e2e_smoke.json",
    "visual_regression": "visual_regression.json",
    "product_kpi": "product_kpi_smoke.json",
}


def load_release_gate_artifacts(
    *,
    artifact_dir: str | Path,
    artifact_files: Mapping[str, str] | None = None,
) -> dict[str, dict[str, object]]:
    resolved_dir = Path(artifact_dir)
    files = dict(DEFAULT_ARTIFACT_FILES)
    if artifact_files is not None:
        files.update({key: value for key, value in artifact_files.items() if key in REQUIRED_GATES})

    loaded: dict[str, dict[str, object]] = {}
    for gate in REQUIRED_GATES:
        artifact_path = resolved_dir / files[gate]
        payload: dict[str, object] | None = None
        error: str | None = None
        if artifact_path.exists():
            try:
                raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                error = f"json_decode_error: {exc.msg}"
            else:
                if isinstance(raw, dict):
                    payload = raw
                else:
                    error = "artifact must be a JSON object"

        loaded[gate] = {"path": str(artifact_path), "payload": payload, "error": error}
    return loaded


def build_release_gate_report(
    *,
    artifacts: Mapping[str, Mapping[str, object]],
    policy: ReleaseGatePolicy | None = None,
    generated_at_utc: datetime | str | None = None,
) -> dict[str, object]:
    active_policy = policy or ReleaseGatePolicy.from_env()
    gate_results: dict[str, dict[str, object]] = {}
    failure_reasons: list[dict[str, str]] = []

    for gate in REQUIRED_GATES:
        result = _evaluate_gate(gate=gate, loaded=artifacts.get(gate) or {}, policy=active_policy)
        gate_results[gate] = result
        if result["status"] == "fail":
            for reason in result["reasons"]:
                if isinstance(reason, dict):
                    failure_reasons.append(
                        {
                            "gate": gate,
                            "code": str(reason.get("code", "unknown")),
                            "message": str(reason.get("message", "")),
                        }
                    )

    release_gate = "fail" if failure_reasons else "pass"
    return {
        "schema_version": RELEASE_GATE_SCHEMA_VERSION,
        "generated_at_utc": normalize_generated_at(generated_at_utc),
        "release_gate": release_gate,
        "blocked": bool(failure_reasons),
        "required_gates": list(REQUIRED_GATES),
        "policy": active_policy.to_dict(),
        "gate_results": gate_results,
        "failure_reasons": failure_reasons,
        "summary": build_summary(release_gate=release_gate, failure_reasons=failure_reasons),
    }


def generate_release_gate_report(
    *,
    artifact_dir: str | Path,
    output_path: str | Path,
    artifact_files: Mapping[str, str] | None = None,
    policy: ReleaseGatePolicy | None = None,
    generated_at_utc: datetime | str | None = None,
) -> dict[str, object]:
    artifacts = load_release_gate_artifacts(artifact_dir=artifact_dir, artifact_files=artifact_files)
    report = build_release_gate_report(artifacts=artifacts, policy=policy, generated_at_utc=generated_at_utc)
    write_release_gate_report(report=report, output_path=output_path)
    return report


def write_release_gate_report(*, report: Mapping[str, object], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def _evaluate_gate(
    *,
    gate: str,
    loaded: Mapping[str, object],
    policy: ReleaseGatePolicy,
) -> dict[str, object]:
    path = str(loaded.get("path") or "")
    payload = loaded.get("payload")
    error = loaded.get("error")

    if error:
        return _failed_result(path=path, reasons=[_reason("artifact_parse_error", f"artifact parse failed: {error}")], details={})
    if not isinstance(payload, Mapping):
        return _failed_result(path=path, reasons=[_reason("missing_artifact", "artifact not found")], details={})

    if gate == "contract":
        return _evaluate_test_gate(
            payload=payload,
            path=path,
            policy=policy,
            failed_keys=("failed_tests", "failed_suites", "failures"),
            flaky_keys=("flaky_tests", "flaky_suites", "flaky"),
        )
    if gate == "e2e":
        return _evaluate_test_gate(
            payload=payload,
            path=path,
            policy=policy,
            failed_keys=("failed_flows", "failed_tests", "failures"),
            flaky_keys=("flaky_flows", "flaky_tests", "flaky"),
        )
    if gate == "visual_regression":
        return _evaluate_visual_gate(payload=payload, path=path, policy=policy)
    return _evaluate_kpi_gate(payload=payload, path=path, policy=policy)


def _evaluate_test_gate(
    *,
    payload: Mapping[str, object],
    path: str,
    policy: ReleaseGatePolicy,
    failed_keys: tuple[str, ...],
    flaky_keys: tuple[str, ...],
) -> dict[str, object]:
    status = normalize_status(payload)
    if status is None:
        return _failed_result(
            path=path,
            reasons=[_reason("artifact_invalid", "status must be pass/fail/flaky or include passed=true/false")],
            details={},
        )

    failed_items = extract_str_list(payload, failed_keys)
    flaky_items = extract_str_list(payload, flaky_keys)
    reasons: list[dict[str, str]] = []
    if status == "fail" or failed_items:
        failed_text = ", ".join(failed_items) if failed_items else "reported"
        reasons.append(_reason("suite_failed", f"failed suites/flows: {failed_text}"))
    if (status == "flaky" or flaky_items) and policy.fail_on_flaky:
        flaky_text = ", ".join(flaky_items) if flaky_items else "reported"
        reasons.append(_reason("flaky_result", f"flaky suites/flows detected: {flaky_text}"))

    details = {"status": status, "failed": failed_items, "flaky": flaky_items}
    if reasons:
        return _failed_result(path=path, reasons=reasons, details=details)
    return _passed_result(path=path, details=details)


def _evaluate_visual_gate(
    *,
    payload: Mapping[str, object],
    path: str,
    policy: ReleaseGatePolicy,
) -> dict[str, object]:
    status = normalize_status(payload)
    diff_ratio = extract_float(payload, keys=("diff_ratio", "pixel_diff_ratio"))
    threshold_ratio = extract_float(payload, keys=("threshold_ratio", "max_diff_ratio"))
    threshold = threshold_ratio if threshold_ratio is not None else policy.visual_max_diff_ratio

    reasons: list[dict[str, str]] = []
    if status is None:
        reasons.append(_reason("artifact_invalid", "status must be pass/fail/flaky or include passed=true/false"))
    if diff_ratio is None:
        reasons.append(_reason("artifact_invalid", "diff_ratio (or pixel_diff_ratio) must be a number"))
    if status == "fail":
        reasons.append(_reason("suite_failed", "visual regression suite failed"))
    if status == "flaky" and policy.fail_on_flaky:
        reasons.append(_reason("flaky_result", "visual regression suite reported flaky result"))
    if diff_ratio is not None and diff_ratio > threshold:
        reasons.append(_reason("threshold_not_met", f"diff_ratio {diff_ratio:.4f} exceeds threshold {threshold:.4f}"))

    details = {"status": status, "diff_ratio": diff_ratio, "threshold": threshold}
    if reasons:
        return _failed_result(path=path, reasons=reasons, details=details)
    return _passed_result(path=path, details=details)


def _evaluate_kpi_gate(
    *,
    payload: Mapping[str, object],
    path: str,
    policy: ReleaseGatePolicy,
) -> dict[str, object]:
    metrics = payload.get("metrics")
    if not isinstance(metrics, Mapping):
        return _failed_result(
            path=path,
            reasons=[_reason("artifact_invalid", "product KPI snapshot must include metrics object")],
            details={},
        )

    reasons: list[dict[str, str]] = []
    if bool(payload.get("overall_low_confidence")):
        reasons.append(_reason("low_confidence", "product KPI snapshot flagged low confidence"))

    thresholds = [
        (CARD_CLICK_RATE, "min", policy.card_click_rate_min),
        (EVIDENCE_CLICK_RATE, "min", policy.evidence_click_rate_min),
        (BRIEF_OPEN_RATE, "min", policy.brief_open_rate_min),
        (INACCURATE_REASON_REPORT_RATE, "max", policy.inaccurate_reason_report_rate_max),
    ]

    checked: dict[str, dict[str, float | None | str]] = {}
    for metric_key, bound, threshold in thresholds:
        value = extract_metric_value(metrics.get(metric_key))
        checked[metric_key] = {"bound": bound, "threshold": threshold, "value": value}
        if value is None:
            reasons.append(_reason("metric_missing", f"{metric_key}.value is missing"))
            continue
        if bound == "min" and value < threshold:
            reasons.append(_reason("threshold_not_met", f"{metric_key} {value:.4f} < minimum {threshold:.4f}"))
        if bound == "max" and value > threshold:
            reasons.append(_reason("threshold_not_met", f"{metric_key} {value:.4f} > maximum {threshold:.4f}"))

    details = {"overall_low_confidence": bool(payload.get("overall_low_confidence")), "checked_metrics": checked}
    if reasons:
        return _failed_result(path=path, reasons=reasons, details=details)
    return _passed_result(path=path, details=details)


def _passed_result(*, path: str, details: Mapping[str, object]) -> dict[str, object]:
    return {"status": "pass", "blocking": False, "artifact_path": path, "reason_codes": [], "reasons": [], "details": dict(details)}


def _failed_result(*, path: str, reasons: list[dict[str, str]], details: Mapping[str, object]) -> dict[str, object]:
    return {
        "status": "fail",
        "blocking": True,
        "artifact_path": path,
        "reason_codes": [reason["code"] for reason in reasons],
        "reasons": reasons,
        "details": dict(details),
    }


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
