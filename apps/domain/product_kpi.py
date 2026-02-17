from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from apps.domain.events import parse_utc_datetime, to_utc_iso

CARD_CLICK_RATE = "card_click_rate"
EVIDENCE_CLICK_RATE = "evidence_click_rate"
INACCURATE_REASON_REPORT_RATE = "inaccurate_reason_report_rate"
BRIEF_OPEN_RATE = "brief_open_rate"

PRODUCT_KPI_METRIC_KEYS = (
    CARD_CLICK_RATE,
    EVIDENCE_CLICK_RATE,
    INACCURATE_REASON_REPORT_RATE,
    BRIEF_OPEN_RATE,
)
PRODUCT_KPI_DEFAULT_MIN_SAMPLES = 20

_FLAG_METRIC_MISSING = "metric_missing"
_FLAG_AGGREGATION_DELAYED = "aggregation_delayed"
_FLAG_SAMPLE_SHORTAGE = "sample_shortage"


@dataclass(frozen=True)
class MetricSample:
    numerator: int | None = None
    denominator: int | None = None


class ProductKpiCollector:
    def __init__(self) -> None:
        self._samples: dict[str, MetricSample] = {}

    def clear(self) -> None:
        self._samples.clear()

    def record_card_impression(self, *, count: int = 1) -> None:
        self._increment(metric_key=CARD_CLICK_RATE, denominator=count)

    def record_card_click(self, *, count: int = 1) -> None:
        self._increment(metric_key=CARD_CLICK_RATE, numerator=count)

    def record_evidence_impression(self, *, count: int = 1) -> None:
        self._increment(metric_key=EVIDENCE_CLICK_RATE, denominator=count)

    def record_evidence_click(self, *, count: int = 1) -> None:
        self._increment(metric_key=EVIDENCE_CLICK_RATE, numerator=count)

    def record_reason_impression(self, *, count: int = 1) -> None:
        self._increment(metric_key=INACCURATE_REASON_REPORT_RATE, denominator=count)

    def record_inaccurate_reason_report(self, *, count: int = 1) -> None:
        self._increment(metric_key=INACCURATE_REASON_REPORT_RATE, numerator=count)

    def record_brief_delivered(self, *, count: int = 1) -> None:
        self._increment(metric_key=BRIEF_OPEN_RATE, denominator=count)

    def record_brief_opened(self, *, count: int = 1) -> None:
        self._increment(metric_key=BRIEF_OPEN_RATE, numerator=count)

    def build_snapshot(
        self,
        *,
        min_samples: int = PRODUCT_KPI_DEFAULT_MIN_SAMPLES,
        delayed_metrics: set[str] | None = None,
        generated_at_utc: datetime | str | None = None,
        previous_snapshot: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return build_product_kpi_snapshot(
            metric_samples=self._samples,
            min_samples=min_samples,
            delayed_metrics=delayed_metrics,
            generated_at_utc=generated_at_utc,
            previous_snapshot=previous_snapshot,
        )

    def _increment(
        self,
        *,
        metric_key: str,
        numerator: int = 0,
        denominator: int = 0,
    ) -> None:
        if metric_key not in PRODUCT_KPI_METRIC_KEYS:
            raise ValueError(f"unsupported metric_key '{metric_key}'")
        safe_numerator = _normalize_non_negative_int(numerator, field_name=f"{metric_key}.numerator")
        safe_denominator = _normalize_non_negative_int(denominator, field_name=f"{metric_key}.denominator")
        current = self._samples.get(metric_key, MetricSample(numerator=0, denominator=0))
        self._samples[metric_key] = MetricSample(
            numerator=(current.numerator or 0) + safe_numerator,
            denominator=(current.denominator or 0) + safe_denominator,
        )


def build_product_kpi_snapshot(
    *,
    metric_samples: Mapping[str, MetricSample | Mapping[str, object]],
    min_samples: int = PRODUCT_KPI_DEFAULT_MIN_SAMPLES,
    delayed_metrics: set[str] | None = None,
    generated_at_utc: datetime | str | None = None,
    previous_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if min_samples < 1:
        raise ValueError("min_samples must be >= 1")

    delayed = delayed_metrics or set()
    metrics_payload: dict[str, dict[str, object]] = {}
    for metric_key in PRODUCT_KPI_METRIC_KEYS:
        sample = metric_samples.get(metric_key)
        metrics_payload[metric_key] = _build_metric_payload(
            metric_key=metric_key,
            sample=sample,
            min_samples=min_samples,
            delayed=metric_key in delayed,
            previous_snapshot=previous_snapshot,
        )

    return {
        "schema_version": 1,
        "generated_at_utc": _normalize_generated_at(generated_at_utc),
        "min_samples": min_samples,
        "metric_count": len(PRODUCT_KPI_METRIC_KEYS),
        "has_previous_snapshot": previous_snapshot is not None,
        "overall_low_confidence": any(bool(metric["low_confidence"]) for metric in metrics_payload.values()),
        "metrics": metrics_payload,
    }


def _build_metric_payload(
    *,
    metric_key: str,
    sample: MetricSample | Mapping[str, object] | None,
    min_samples: int,
    delayed: bool,
    previous_snapshot: Mapping[str, object] | None,
) -> dict[str, object]:
    previous_value = _read_previous_value(previous_snapshot=previous_snapshot, metric_key=metric_key)
    flags: list[str] = []
    if delayed:
        flags.append(_FLAG_AGGREGATION_DELAYED)

    if sample is None:
        flags = _append_flag(flags, _FLAG_METRIC_MISSING)
        return {
            "numerator": None,
            "denominator": None,
            "value": None,
            "previous_value": previous_value,
            "delta": None,
            "low_confidence": True,
            "flags": flags,
        }

    numerator, denominator = _coerce_metric_sample(sample, metric_key=metric_key)
    denominator_for_rate = denominator
    if denominator < numerator:
        flags = _append_flag(flags, _FLAG_AGGREGATION_DELAYED)
        denominator_for_rate = numerator
    if denominator_for_rate < min_samples:
        flags = _append_flag(flags, _FLAG_SAMPLE_SHORTAGE)

    value = round(numerator / denominator_for_rate, 4) if denominator_for_rate > 0 else 0.0
    delta = round(value - previous_value, 4) if previous_value is not None else None
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": value,
        "previous_value": previous_value,
        "delta": delta,
        "low_confidence": bool(flags),
        "flags": flags,
    }


def _coerce_metric_sample(
    sample: MetricSample | Mapping[str, object],
    *,
    metric_key: str,
) -> tuple[int, int]:
    if isinstance(sample, MetricSample):
        numerator = sample.numerator
        denominator = sample.denominator
    else:
        numerator = sample.get("numerator")
        denominator = sample.get("denominator")

    safe_numerator = _normalize_non_negative_int(numerator, field_name=f"{metric_key}.numerator")
    safe_denominator = _normalize_non_negative_int(denominator, field_name=f"{metric_key}.denominator")
    return safe_numerator, safe_denominator


def _normalize_non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _normalize_generated_at(value: datetime | str | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    else:
        parsed = parse_utc_datetime(value)
    return to_utc_iso(parsed)


def _read_previous_value(
    *,
    previous_snapshot: Mapping[str, object] | None,
    metric_key: str,
) -> float | None:
    if previous_snapshot is None:
        return None
    metrics = previous_snapshot.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    metric = metrics.get(metric_key)
    if not isinstance(metric, Mapping):
        return None
    value = metric.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 4)


def _append_flag(flags: list[str], flag: str) -> list[str]:
    if flag in flags:
        return flags
    return [*flags, flag]
