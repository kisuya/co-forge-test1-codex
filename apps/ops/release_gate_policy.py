from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ReleaseGatePolicy:
    visual_max_diff_ratio: float
    card_click_rate_min: float
    evidence_click_rate_min: float
    brief_open_rate_min: float
    inaccurate_reason_report_rate_max: float
    fail_on_flaky: bool

    @classmethod
    def from_env(cls) -> "ReleaseGatePolicy":
        return cls(
            visual_max_diff_ratio=_parse_float(
                os.getenv("RELEASE_GATE_VISUAL_MAX_DIFF_RATIO"),
                fallback=0.01,
                variable_name="RELEASE_GATE_VISUAL_MAX_DIFF_RATIO",
                minimum=0.0,
            ),
            card_click_rate_min=_parse_float(
                os.getenv("RELEASE_GATE_CARD_CLICK_RATE_MIN"),
                fallback=0.20,
                variable_name="RELEASE_GATE_CARD_CLICK_RATE_MIN",
                minimum=0.0,
            ),
            evidence_click_rate_min=_parse_float(
                os.getenv("RELEASE_GATE_EVIDENCE_CLICK_RATE_MIN"),
                fallback=0.20,
                variable_name="RELEASE_GATE_EVIDENCE_CLICK_RATE_MIN",
                minimum=0.0,
            ),
            brief_open_rate_min=_parse_float(
                os.getenv("RELEASE_GATE_BRIEF_OPEN_RATE_MIN"),
                fallback=0.20,
                variable_name="RELEASE_GATE_BRIEF_OPEN_RATE_MIN",
                minimum=0.0,
            ),
            inaccurate_reason_report_rate_max=_parse_float(
                os.getenv("RELEASE_GATE_INACCURATE_REASON_REPORT_RATE_MAX"),
                fallback=0.50,
                variable_name="RELEASE_GATE_INACCURATE_REASON_REPORT_RATE_MAX",
                minimum=0.0,
            ),
            fail_on_flaky=_parse_bool(
                os.getenv("RELEASE_GATE_FAIL_ON_FLAKY"),
                fallback=True,
                variable_name="RELEASE_GATE_FAIL_ON_FLAKY",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "visual_max_diff_ratio": self.visual_max_diff_ratio,
            "card_click_rate_min": self.card_click_rate_min,
            "evidence_click_rate_min": self.evidence_click_rate_min,
            "brief_open_rate_min": self.brief_open_rate_min,
            "inaccurate_reason_report_rate_max": self.inaccurate_reason_report_rate_max,
            "fail_on_flaky": self.fail_on_flaky,
        }


def _parse_float(
    value: str | None,
    *,
    fallback: float,
    variable_name: str,
    minimum: float,
) -> float:
    if value is None or value.strip() == "":
        return fallback
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{variable_name} must be a float") from exc
    if parsed < minimum:
        raise ValueError(f"{variable_name} must be >= {minimum}")
    return parsed


def _parse_bool(
    value: str | None,
    *,
    fallback: bool,
    variable_name: str,
) -> bool:
    if value is None or value.strip() == "":
        return fallback
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{variable_name} must be a boolean-like value")
