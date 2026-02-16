from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.notifications_db import notification_db_service


def register_notification_routes(app: FastAPI) -> None:
    @app.get("/v1/notifications")
    def list_in_app_notifications(request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        notifications = notification_db_service.list_in_app_notifications(user_id=user.user_id)
        unread_count = notification_db_service.count_unread_in_app_notifications(user_id=user.user_id)
        return {
            "items": [item.to_dict() for item in notifications],
            "unread_count": unread_count,
        }

    @app.patch("/v1/notifications/{notification_id}/read")
    def mark_notification_read(notification_id: str, request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        notification = notification_db_service.mark_in_app_notification_read(
            notification_id=notification_id,
            user_id=user.user_id,
        )
        if notification is None:
            raise HTTPException(
                status_code=404,
                code="notification_not_found",
                message="Notification not found",
                details={"notification_id": notification_id},
            )
        unread_count = notification_db_service.count_unread_in_app_notifications(user_id=user.user_id)
        return {"notification": notification.to_dict(), "unread_count": unread_count}
