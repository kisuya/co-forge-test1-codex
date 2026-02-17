from __future__ import annotations

import unittest

from apps.worker.brief_delivery_scheduler import BriefDeliveryPolicy, schedule_brief_deliveries


class BriefDeliverySchedulerTests(unittest.TestCase):
    def test_schedules_pre_and_post_briefs_by_market_boundary(self) -> None:
        result = schedule_brief_deliveries(
            user_settings=[
                {
                    "user_id": "user-schedule-1",
                    "markets": ["US"],
                    "channels": ["in_app", "email"],
                }
            ],
            pre_market_briefs=[
                {
                    "brief_id": "pre-1",
                    "user_id": "user-schedule-1",
                    "market": "US",
                    "trade_date_local": "2026-02-18",
                }
            ],
            post_close_briefs=[
                {
                    "brief_id": "post-1",
                    "user_id": "user-schedule-1",
                    "market": "US",
                    "trade_date_local": "2026-02-18",
                }
            ],
            existing_jobs=[],
            channel_failures=[],
            now_utc="2026-02-17T00:00:00Z",
            policy=BriefDeliveryPolicy(
                pre_market_lead_minutes=45,
                post_close_delay_minutes=20,
                retry_delay_minutes=5,
                max_retry_attempts=3,
            ),
        )

        self.assertIsNone(result["fallback_reason"])
        jobs = result["scheduled_jobs"]
        self.assertEqual(len(jobs), 4)

        pre_email = next(
            job for job in jobs if job["brief_type"] == "pre_market" and job["channel"] == "email"
        )
        post_email = next(
            job for job in jobs if job["brief_type"] == "post_close" and job["channel"] == "email"
        )
        self.assertEqual(pre_email["scheduled_for_utc"], "2026-02-18T13:45:00Z")
        self.assertEqual(post_email["scheduled_for_utc"], "2026-02-18T21:20:00Z")
        self.assertEqual(result["skipped_duplicates"], [])

    def test_skips_duplicate_brief_jobs_using_dedupe_key(self) -> None:
        result = schedule_brief_deliveries(
            user_settings=[
                {
                    "user_id": "user-schedule-2",
                    "markets": ["US"],
                    "channels": ["in_app", "email"],
                }
            ],
            pre_market_briefs=[
                {
                    "brief_id": "pre-2",
                    "user_id": "user-schedule-2",
                    "market": "US",
                    "trade_date_local": "2026-02-19",
                }
            ],
            post_close_briefs=[],
            existing_jobs=[
                {
                    "dedupe_key": "user-schedule-2:pre_market:US:2026-02-19:in_app",
                    "status": "scheduled",
                }
            ],
            channel_failures=[],
            now_utc="2026-02-18T00:00:00Z",
            policy=BriefDeliveryPolicy(
                pre_market_lead_minutes=30,
                post_close_delay_minutes=10,
                retry_delay_minutes=5,
                max_retry_attempts=3,
            ),
        )

        jobs = result["scheduled_jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["channel"], "email")
        self.assertEqual(
            result["skipped_duplicates"],
            ["user-schedule-2:pre_market:US:2026-02-19:in_app"],
        )

    def test_channel_failures_trigger_retry_or_compensation(self) -> None:
        result = schedule_brief_deliveries(
            user_settings=[],
            pre_market_briefs=[],
            post_close_briefs=[],
            existing_jobs=[],
            channel_failures=[
                {
                    "dedupe_key": "u1:post_close:US:2026-02-18:email",
                    "channel": "email",
                    "attempt": 1,
                    "retryable": True,
                    "error": "smtp timeout",
                },
                {
                    "dedupe_key": "u1:post_close:US:2026-02-18:in_app",
                    "channel": "in_app",
                    "attempt": 2,
                    "retryable": False,
                    "error": "template missing",
                },
            ],
            now_utc="2026-02-18T22:00:00Z",
            policy=BriefDeliveryPolicy(
                pre_market_lead_minutes=45,
                post_close_delay_minutes=20,
                retry_delay_minutes=10,
                max_retry_attempts=2,
            ),
        )

        retry_jobs = result["retry_jobs"]
        compensations = result["compensations"]

        self.assertEqual(len(retry_jobs), 1)
        self.assertEqual(retry_jobs[0]["dedupe_key"], "u1:post_close:US:2026-02-18:email")
        self.assertEqual(retry_jobs[0]["attempt"], 2)
        self.assertEqual(retry_jobs[0]["scheduled_for_utc"], "2026-02-18T22:10:00Z")

        self.assertEqual(len(compensations), 1)
        self.assertEqual(compensations[0]["dedupe_key"], "u1:post_close:US:2026-02-18:in_app")
        self.assertEqual(compensations[0]["action"], "mark_failed")

if __name__ == "__main__":
    unittest.main()
