"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Toast } from "@/components/toast";
import {
  ApiClientError,
  type ApiClient,
  type NotificationItem,
  type ThresholdItem,
} from "@/lib/api-client";

type LoadStatus = "loading" | "success" | "error";

type SettingsCenterProps = {
  client: ApiClient;
};

function toNotificationStatusLabel(status: string): string {
  if (status === "cooldown") {
    return "쿨다운 중";
  }
  if (status === "read") {
    return "read";
  }
  return status;
}

export function SettingsCenter({ client }: SettingsCenterProps): JSX.Element {
  const [notificationsStatus, setNotificationsStatus] = useState<LoadStatus>("loading");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationsError, setNotificationsError] = useState("");

  const [thresholdStatus, setThresholdStatus] = useState<LoadStatus>("loading");
  const [thresholds, setThresholds] = useState<ThresholdItem[]>([]);
  const [thresholdError, setThresholdError] = useState("");

  const [windowMinutes, setWindowMinutes] = useState(5);
  const [thresholdPct, setThresholdPct] = useState("3");
  const [toast, setToast] = useState<{ kind: "error" | "success"; message: string } | null>(null);

  async function loadNotifications(): Promise<void> {
    setNotificationsStatus("loading");
    setNotificationsError("");
    try {
      const response = await client.listNotifications();
      setNotifications(response.items);
      setUnreadCount(response.unread_count);
      setNotificationsStatus("success");
    } catch (error) {
      const message =
        error instanceof ApiClientError ? error.payload.message : "알림을 불러오지 못했습니다.";
      setNotificationsError(message);
      setNotificationsStatus("error");
    }
  }

  async function loadThresholds(): Promise<void> {
    setThresholdStatus("loading");
    setThresholdError("");
    try {
      const response = await client.listThresholds();
      setThresholds(response.items);
      setThresholdStatus("success");
    } catch (error) {
      const message =
        error instanceof ApiClientError ? error.payload.message : "임계값을 불러오지 못했습니다.";
      setThresholdError(message);
      setThresholdStatus("error");
    }
  }

  useEffect(() => {
    void loadNotifications();
    void loadThresholds();
  }, []);

  async function handleMarkRead(notificationId: string): Promise<void> {
    setToast(null);
    const previousItems = notifications;
    const previousUnread = unreadCount;

    setNotifications((items) =>
      items.map((item) =>
        item.id === notificationId
          ? {
              ...item,
              status: "read",
            }
          : item,
      ),
    );
    setUnreadCount((count) => Math.max(0, count - 1));

    try {
      const response = await client.markNotificationRead(notificationId);
      setNotifications((items) =>
        items.map((item) => (item.id === notificationId ? response.notification : item)),
      );
      setUnreadCount(response.unread_count);
      setToast({ kind: "success", message: "알림을 읽음 처리했습니다." });
    } catch (error) {
      setNotifications(previousItems);
      setUnreadCount(previousUnread);
      const message =
        error instanceof ApiClientError ? error.payload.message : "알림 읽음 처리에 실패했습니다.";
      setToast({ kind: "error", message });
    }
  }

  async function handleThresholdSave(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setToast(null);

    const parsedThreshold = Number(thresholdPct);
    if (!Number.isFinite(parsedThreshold)) {
      setToast({ kind: "error", message: "임계값은 숫자로 입력해야 합니다." });
      return;
    }

    try {
      const response = await client.upsertThreshold({
        windowMinutes,
        thresholdPct: parsedThreshold,
      });
      setThresholds((items) => {
        const next = [...items];
        const found = next.findIndex((item) => item.window_minutes === response.threshold.window_minutes);
        if (found >= 0) {
          next[found] = response.threshold;
        } else {
          next.push(response.threshold);
        }
        return next.sort((a, b) => a.window_minutes - b.window_minutes);
      });
      setToast({ kind: "success", message: "임계값이 저장되었습니다." });
    } catch (error) {
      const message =
        error instanceof ApiClientError ? error.payload.message : "임계값 저장에 실패했습니다.";
      setToast({ kind: "error", message });
    }
  }

  return (
    <section style={{ border: "1px solid #cbd5e1", borderRadius: 12, background: "#fff", padding: 16 }}>
      <h2 style={{ marginTop: 0 }}>설정 센터</h2>
      <div style={{ display: "grid", gap: 16 }}>
        <div>
          <h3 style={{ marginBottom: 8 }}>알림 센터</h3>
          <p style={{ marginTop: 0 }}>읽지 않은 알림: {unreadCount}</p>
          {notificationsStatus === "loading" ? <p>알림 로딩 중...</p> : null}
          {notificationsStatus === "error" ? <p role="alert">{notificationsError}</p> : null}
          {notificationsStatus === "success" && notifications.length === 0 ? <p>알림이 없습니다.</p> : null}
          {notificationsStatus === "success" && notifications.length > 0 ? (
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <span>{notification.message}</span>{" "}
                  <strong>{toNotificationStatusLabel(notification.status)}</strong>{" "}
                  {notification.status === "read" ? null : (
                    <button type="button" onClick={() => void handleMarkRead(notification.id)}>
                      읽음
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div>
          <h3 style={{ marginBottom: 8 }}>사용자 임계값</h3>
          <form onSubmit={handleThresholdSave} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select
              aria-label="임계값 윈도우"
              value={windowMinutes}
              onChange={(event) => setWindowMinutes(Number(event.currentTarget.value))}
            >
              <option value={5}>5분</option>
              <option value={1440}>1일</option>
            </select>
            <input
              aria-label="임계값 퍼센트"
              value={thresholdPct}
              onChange={(event) => setThresholdPct(event.currentTarget.value)}
              placeholder="예: 3"
            />
            <button type="submit">저장</button>
          </form>

          {thresholdStatus === "loading" ? <p>임계값 로딩 중...</p> : null}
          {thresholdStatus === "error" ? <p role="alert">{thresholdError}</p> : null}
          {thresholdStatus === "success" && thresholds.length === 0 ? <p>저장된 임계값이 없습니다.</p> : null}
          {thresholdStatus === "success" && thresholds.length > 0 ? (
            <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
              {thresholds.map((threshold) => (
                <li key={threshold.window_minutes}>
                  {threshold.window_minutes}분: ±{threshold.threshold_pct}%
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      {toast ? <Toast kind={toast.kind} message={toast.message} /> : null}
    </section>
  );
}
