from __future__ import annotations

import math

_MARKET_CURRENCIES = {
    "KR": "KRW",
    "US": "USD",
}


def estimate_portfolio_event_impact(
    *,
    market: str,
    qty: float,
    avg_price: float,
    change_pct: float,
    fx_rate: float | None = None,
    target_currency: str | None = None,
) -> dict[str, object]:
    normalized_market = _normalize_market(market)
    normalized_qty = _normalize_positive_float(qty, field_name="qty")
    normalized_avg_price = _normalize_positive_float(avg_price, field_name="avg_price")
    normalized_change_pct = _normalize_finite_float(change_pct, field_name="change_pct")

    exposure_amount = round(normalized_qty * normalized_avg_price, 4)
    pnl_in_source_currency = round(exposure_amount * (normalized_change_pct / 100.0), 4)
    source_currency = _MARKET_CURRENCIES[normalized_market]

    effective_currency = source_currency
    estimated_pnl_amount = pnl_in_source_currency
    fx_applied = False

    if fx_rate is not None:
        normalized_fx_rate = _normalize_positive_float(fx_rate, field_name="fx_rate")
        normalized_target_currency = _normalize_currency(target_currency, fallback=source_currency)
        if normalized_target_currency != source_currency:
            effective_currency = normalized_target_currency
            estimated_pnl_amount = round(pnl_in_source_currency * normalized_fx_rate, 4)
            fx_applied = True

    return {
        "market": normalized_market,
        "currency": effective_currency,
        "source_currency": source_currency,
        "fx_applied": fx_applied,
        "qty": normalized_qty,
        "avg_price": normalized_avg_price,
        "change_pct": normalized_change_pct,
        "exposure_amount": exposure_amount,
        "estimated_pnl_amount": estimated_pnl_amount,
        "estimated_pnl_ratio_pct": normalized_change_pct,
    }


def _normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in _MARKET_CURRENCIES:
        raise ValueError("market must be KR or US")
    return normalized


def _normalize_positive_float(raw: float, *, field_name: str) -> float:
    value = _normalize_finite_float(raw, field_name=field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _normalize_finite_float(raw: float, *, field_name: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return round(value, 8)


def _normalize_currency(currency: str | None, *, fallback: str) -> str:
    normalized = (currency or fallback).strip().upper()
    return normalized or fallback
