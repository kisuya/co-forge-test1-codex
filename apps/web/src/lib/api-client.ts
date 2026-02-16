import type { AuthSession } from "@/lib/auth-session";

export type ApiErrorPayload = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
  retryable?: boolean;
};

export type AuthResponse = {
  user_id: string;
  access_token: string;
};

export type AuthMeResponse = {
  user: {
    id: string;
    email: string | null;
  };
};

export type WatchlistItem = {
  id: string;
  user_id: string;
  symbol: string;
  market: string;
  created_at_utc: string;
};

export type WatchlistListResponse = {
  items: WatchlistItem[];
  total: number;
  page: number;
  size: number;
};

export type EventReason = {
  id: string;
  rank: number;
  reason_type: string;
  confidence_score: number;
  summary: string;
  source_url: string | null;
  published_at: string;
  explanation: Record<string, unknown>;
};

export type EventPayload = {
  id: string;
  symbol: string;
  market: string;
  change_pct: number;
  window_minutes: number;
  detected_at_utc: string;
  exchange_timezone: string;
  session_label: string;
  reasons: EventReason[];
  portfolio_impact: Record<string, unknown> | null;
};

export type EventsListResponse = {
  items: EventPayload[];
  count: number;
  next_cursor: string | null;
};

export type EventDetailResponse = {
  event: EventPayload;
};

export type NotificationItem = {
  id: string;
  user_id: string;
  event_id: string;
  channel: string;
  status: string;
  message: string;
  sent_at_utc: string;
};

export type NotificationListResponse = {
  items: NotificationItem[];
  unread_count: number;
};

export type ThresholdItem = {
  user_id: string;
  window_minutes: number;
  threshold_pct: number;
};

export type ThresholdListResponse = {
  items: ThresholdItem[];
  count: number;
};

export class ApiClientError extends Error {
  readonly status: number;
  readonly payload: ApiErrorPayload;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message || "API request failed");
    this.name = "ApiClientError";
    this.status = status;
    this.payload = payload;
  }
}

export class SessionExpiredError extends ApiClientError {
  constructor(payload: ApiErrorPayload) {
    super(401, payload);
    this.name = "SessionExpiredError";
  }
}

type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE";

type RequestOptions = {
  method?: HttpMethod;
  body?: Record<string, unknown>;
  requireAuth?: boolean;
};

export type ApiClient = {
  signup: (input: { email: string; password: string }) => Promise<AuthResponse>;
  login: (input: { email: string; password: string }) => Promise<AuthResponse>;
  getMe: () => Promise<AuthMeResponse>;
  listWatchlistItems: (input?: { page?: number; size?: number }) => Promise<WatchlistListResponse>;
  createWatchlistItem: (input: { symbol: string; market: "KR" | "US" }) => Promise<{
    item: WatchlistItem;
    is_duplicate: boolean;
  }>;
  deleteWatchlistItem: (itemId: string) => Promise<{ deleted: boolean; item_id: string }>;
  listEvents: (input?: { size?: number; cursor?: string }) => Promise<EventsListResponse>;
  getEventDetail: (eventId: string) => Promise<EventDetailResponse>;
  submitReasonFeedback: (input: {
    eventId: string;
    reasonId: string;
    feedback: "helpful" | "not_helpful";
  }) => Promise<{ feedback: Record<string, unknown>; overwritten: boolean }>;
  listNotifications: () => Promise<NotificationListResponse>;
  markNotificationRead: (notificationId: string) => Promise<{
    notification: NotificationItem;
    unread_count: number;
  }>;
  listThresholds: () => Promise<ThresholdListResponse>;
  upsertThreshold: (input: { windowMinutes: number; thresholdPct: number }) => Promise<{
    threshold: ThresholdItem;
  }>;
  logout: () => void;
};

type ApiClientOptions = {
  baseUrl: string;
  session: AuthSession;
  fetchImpl?: typeof fetch;
  onSessionExpired?: () => void;
};

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/$/, "");
}

function makeDefaultPayload(message: string): ApiErrorPayload {
  return {
    code: "unknown_error",
    message,
    details: {},
    retryable: false,
  };
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const fetchImpl = options.fetchImpl ?? fetch;

  async function request<T>(path: string, requestOptions: RequestOptions = {}): Promise<T> {
    const method = requestOptions.method ?? "GET";
    const state = options.session.get();
    const headers: Record<string, string> = {
      "content-type": "application/json",
    };

    if (requestOptions.requireAuth && state?.accessToken) {
      headers.authorization = `Bearer ${state.accessToken}`;
    }

    const response = await fetchImpl(`${baseUrl}${path}`, {
      method,
      headers,
      body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
    });

    const data = await response
      .json()
      .catch(() => makeDefaultPayload("Unexpected response format"));

    if (!response.ok) {
      const payload = (data || makeDefaultPayload("Request failed")) as ApiErrorPayload;
      if (response.status === 401 && payload.code === "invalid_token") {
        options.session.clear();
        options.onSessionExpired?.();
        throw new SessionExpiredError(payload);
      }
      throw new ApiClientError(response.status, payload);
    }

    return data as T;
  }

  return {
    signup: async ({ email, password }) => {
      const result = await request<AuthResponse>("/v1/auth/signup", {
        method: "POST",
        body: { email, password },
      });
      options.session.set({ userId: result.user_id, accessToken: result.access_token });
      return result;
    },
    login: async ({ email, password }) => {
      const result = await request<AuthResponse>("/v1/auth/login", {
        method: "POST",
        body: { email, password },
      });
      options.session.set({ userId: result.user_id, accessToken: result.access_token });
      return result;
    },
    getMe: () => request<AuthMeResponse>("/v1/auth/me", { requireAuth: true }),
    listWatchlistItems: ({ page = 1, size = 20 } = {}) =>
      request<WatchlistListResponse>(`/v1/watchlists/items?page=${page}&size=${size}`, { requireAuth: true }),
    createWatchlistItem: ({ symbol, market }) =>
      request<{ item: WatchlistItem; is_duplicate: boolean }>("/v1/watchlists/items", {
        method: "POST",
        body: { symbol, market },
        requireAuth: true,
      }),
    deleteWatchlistItem: (itemId) =>
      request<{ deleted: boolean; item_id: string }>(`/v1/watchlists/items/${itemId}`, {
        method: "DELETE",
        requireAuth: true,
      }),
    listEvents: ({ size = 20, cursor } = {}) => {
      const query = cursor ? `?size=${size}&cursor=${encodeURIComponent(cursor)}` : `?size=${size}`;
      return request<EventsListResponse>(`/v1/events${query}`, { requireAuth: true });
    },
    getEventDetail: (eventId) => request<EventDetailResponse>(`/v1/events/${eventId}`, { requireAuth: true }),
    submitReasonFeedback: ({ eventId, reasonId, feedback }) =>
      request<{ feedback: Record<string, unknown>; overwritten: boolean }>(`/v1/events/${eventId}/feedback`, {
        method: "POST",
        body: { reason_id: reasonId, feedback },
        requireAuth: true,
      }),
    listNotifications: () => request<NotificationListResponse>("/v1/notifications", { requireAuth: true }),
    markNotificationRead: (notificationId) =>
      request<{ notification: NotificationItem; unread_count: number }>(
        `/v1/notifications/${notificationId}/read`,
        {
          method: "PATCH",
          requireAuth: true,
        },
      ),
    listThresholds: () => request<ThresholdListResponse>("/v1/thresholds", { requireAuth: true }),
    upsertThreshold: ({ windowMinutes, thresholdPct }) =>
      request<{ threshold: ThresholdItem }>("/v1/thresholds", {
        method: "POST",
        body: { window_minutes: windowMinutes, threshold_pct: thresholdPct },
        requireAuth: true,
      }),
    logout: () => {
      options.session.clear();
      options.onSessionExpired?.();
    },
  };
}
