from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_WINDOWS = {5, 1440}
_MAX_THRESHOLD_PCT = 50.0


@dataclass(frozen=True)
class UserThreshold:
    user_id: str
    window_minutes: int
    threshold_pct: float

    def to_dict(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "window_minutes": self.window_minutes,
            "threshold_pct": self.threshold_pct,
        }


class UserThresholdStore:
    def __init__(self) -> None:
        self._thresholds: dict[tuple[str, int], float] = {}

    def set_threshold(self, *, user_id: str, window_minutes: int, threshold_pct: float) -> UserThreshold:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_window = _normalize_window_minutes(window_minutes)
        normalized_threshold = _normalize_threshold_pct(threshold_pct)
        self._thresholds[(normalized_user_id, normalized_window)] = normalized_threshold
        return UserThreshold(
            user_id=normalized_user_id,
            window_minutes=normalized_window,
            threshold_pct=normalized_threshold,
        )

    def get_threshold(self, *, user_id: str, window_minutes: int) -> float | None:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_window = _normalize_window_minutes(window_minutes)
        return self._thresholds.get((normalized_user_id, normalized_window))

    def list_thresholds(self, *, user_id: str) -> list[UserThreshold]:
        normalized_user_id = _normalize_user_id(user_id)
        matches: list[UserThreshold] = []
        for (stored_user_id, window_minutes), threshold_pct in self._thresholds.items():
            if stored_user_id != normalized_user_id:
                continue
            matches.append(
                UserThreshold(
                    user_id=stored_user_id,
                    window_minutes=window_minutes,
                    threshold_pct=threshold_pct,
                )
            )
        return sorted(matches, key=lambda item: item.window_minutes)

    def clear(self) -> None:
        self._thresholds.clear()


def _normalize_user_id(user_id: str) -> str:
    normalized = (user_id or "").strip()
    if not normalized:
        raise ValueError("user_id must not be empty")
    return normalized


def _normalize_window_minutes(window_minutes: int) -> int:
    if window_minutes not in _DEFAULT_WINDOWS:
        raise ValueError("window_minutes must be one of 5 or 1440")
    return window_minutes


def _normalize_threshold_pct(threshold_pct: float) -> float:
    if threshold_pct <= 0 or threshold_pct > _MAX_THRESHOLD_PCT:
        raise ValueError("threshold_pct must be > 0 and <= 50")
    return round(float(threshold_pct), 4)


user_threshold_store = UserThresholdStore()
