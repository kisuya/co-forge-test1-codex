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

export type SymbolSearchItem = {
  ticker: string;
  name: string;
  market: "KR" | "US";
};

export type SymbolSearchResponse = {
  items: SymbolSearchItem[];
  count: number;
  catalog_version: string | null;
  catalog_refreshed_at_utc: string | null;
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

export type ReasonStatus = "collecting_evidence" | "verified";

export type ConfidenceComponentBreakdown = {
  source_reliability: number;
  event_match: number;
  time_proximity: number;
};

export type ConfidenceBreakdown = {
  weights: ConfidenceComponentBreakdown;
  signals: ConfidenceComponentBreakdown;
  score_breakdown: ConfidenceComponentBreakdown & { total: number };
};

export type ReasonReportStatus = "received" | "reviewed" | "resolved";

export type ReasonRevision = {
  id: string;
  report_id: string;
  event_id: string;
  reason_id: string;
  revision_reason: string;
  confidence_before: number;
  confidence_after: number;
  revised_at_utc: string;
};

export type ReasonStatusTransition = {
  report_id: string;
  event_id: string;
  reason_id: string;
  from_status: ReasonReportStatus | null;
  to_status: ReasonReportStatus;
  changed_at_utc: string;
  note: string | null;
};

export type ReasonRevisionHistoryResponse = {
  event_id: string;
  revision_history: ReasonRevision[];
  status_transitions: ReasonStatusTransition[];
  count: number;
  meta: {
    has_revision_history: boolean;
    latest_status: ReasonReportStatus | null;
  };
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
  reason_status?: ReasonStatus;
  confidence_breakdown?: ConfidenceBreakdown;
  explanation_text?: string;
  revision_hint?: string | null;
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

export type BriefType = "pre_market" | "post_close";
export type BriefStatus = "unread" | "read";

export type BriefSummaryItem = {
  id: string;
  brief_type: BriefType;
  title: string;
  summary: string;
  generated_at_utc: string;
  markets: string[];
  item_count: number;
  fallback_reason: string | null;
  status: BriefStatus;
  is_expired: boolean;
};

export type BriefContentItem = {
  event_id: string;
  symbol: string;
  market: string;
  summary: string;
  event_detail_url: string;
  source_url: string;
};

export type BriefListResponse = {
  items: BriefSummaryItem[];
  count: number;
  meta: {
    unread_count: number;
    pre_market_count: number;
    post_close_count: number;
  };
};

export type BriefDetailResponse = {
  brief: BriefSummaryItem & {
    items: BriefContentItem[];
  };
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
  searchSymbols: (input: { query: string; market: "KR" | "US" }) => Promise<SymbolSearchResponse>;
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
  submitReasonReport: (input: {
    eventId: string;
    reasonId: string;
    reportType: "inaccurate_reason" | "wrong_source" | "outdated_information" | "other";
    note?: string;
  }) => Promise<{ report_id: string; status: ReasonReportStatus; queued: boolean }>;
  listReasonRevisions: (eventId: string) => Promise<ReasonRevisionHistoryResponse>;
  listBriefs: (input?: { size?: number }) => Promise<BriefListResponse>;
  getBriefDetail: (briefId: string) => Promise<BriefDetailResponse>;
  markBriefRead: (briefId: string) => Promise<{
    brief: BriefSummaryItem;
    unread_count: number;
  }>;
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
    searchSymbols: ({ query, market }) =>
      request<SymbolSearchResponse>(
        `/v1/symbols/search?q=${encodeURIComponent(query)}&market=${encodeURIComponent(market)}`,
        { requireAuth: true },
      ),
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
    submitReasonReport: ({ eventId, reasonId, reportType, note = "" }) =>
      request<{ report_id: string; status: ReasonReportStatus; queued: boolean }>(
        `/v1/events/${eventId}/reason-reports`,
        {
          method: "POST",
          body: { reason_id: reasonId, report_type: reportType, note },
          requireAuth: true,
        },
      ),
    listReasonRevisions: (eventId) =>
      request<ReasonRevisionHistoryResponse>(`/v1/events/${eventId}/reason-revisions`, { requireAuth: true }),
    listBriefs: ({ size = 20 } = {}) =>
      request<BriefListResponse>(`/v1/briefs?size=${size}`, { requireAuth: true }),
    getBriefDetail: (briefId) => request<BriefDetailResponse>(`/v1/briefs/${briefId}`, { requireAuth: true }),
    markBriefRead: (briefId) =>
      request<{ brief: BriefSummaryItem; unread_count: number }>(`/v1/briefs/${briefId}/read`, {
        method: "PATCH",
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
