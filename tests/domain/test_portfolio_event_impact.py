from __future__ import annotations

import unittest

from apps.domain.portfolio_impact import estimate_portfolio_event_impact


class PortfolioEventImpactTests(unittest.TestCase):
    def test_uses_market_default_currency_when_fx_is_missing(self) -> None:
        impact = estimate_portfolio_event_impact(
            market="US",
            qty=10,
            avg_price=100,
            change_pct=5,
        )

        self.assertEqual(impact["currency"], "USD")
        self.assertEqual(impact["source_currency"], "USD")
        self.assertFalse(impact["fx_applied"])
        self.assertEqual(impact["exposure_amount"], 1000.0)
        self.assertEqual(impact["estimated_pnl_amount"], 50.0)
        self.assertEqual(impact["estimated_pnl_ratio_pct"], 5.0)

    def test_applies_fx_rate_when_target_currency_differs(self) -> None:
        impact = estimate_portfolio_event_impact(
            market="US",
            qty=2,
            avg_price=100,
            change_pct=10,
            fx_rate=1300,
            target_currency="KRW",
        )

        self.assertEqual(impact["currency"], "KRW")
        self.assertEqual(impact["source_currency"], "USD")
        self.assertTrue(impact["fx_applied"])
        self.assertEqual(impact["estimated_pnl_amount"], 26000.0)
        self.assertEqual(impact["estimated_pnl_ratio_pct"], 10.0)

    def test_invalid_qty_or_avg_price_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            estimate_portfolio_event_impact(
                market="KR",
                qty=0,
                avg_price=70000,
                change_pct=3,
            )

        with self.assertRaises(ValueError):
            estimate_portfolio_event_impact(
                market="KR",
                qty=2,
                avg_price=-1,
                change_pct=3,
            )


if __name__ == "__main__":
    unittest.main()
