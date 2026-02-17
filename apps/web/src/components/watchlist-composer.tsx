"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { ApiClientError, type ApiClient, type SymbolSearchItem, type WatchlistItem } from "@/lib/api-client";

type LoadStatus = "loading" | "success" | "error";
type SearchStatus = "idle" | "loading" | "success" | "error";
type UiError = { message: string; retryable: boolean };
type ToastPayload = { kind: "error" | "success"; message: string };
type SubmitError = { candidate: SymbolSearchItem; message: string };

type WatchlistComposerProps = {
  client: ApiClient;
  onToast: (toast: ToastPayload) => void;
};

const MIN_QUERY_LENGTH = 2;
const MAX_QUERY_LENGTH = 20;
const SEARCH_DEBOUNCE_MS = 150;
const RECENT_SEARCH_LIMIT = 5;
const RECENT_SEARCH_STORAGE_KEY = "oh-my-stock.watchlist.recent.v1";

const FALLBACK_SYMBOLS: SymbolSearchItem[] = [
  { ticker: "AAPL", name: "Apple Inc.", market: "US" },
  { ticker: "MSFT", name: "Microsoft Corporation", market: "US" },
  { ticker: "META", name: "Meta Platforms", market: "US" },
  { ticker: "NVDA", name: "NVIDIA Corporation", market: "US" },
  { ticker: "TSLA", name: "Tesla Inc.", market: "US" },
  { ticker: "005930", name: "Samsung Electronics", market: "KR" },
  { ticker: "000660", name: "SK Hynix", market: "KR" },
  { ticker: "035420", name: "NAVER", market: "KR" },
];

function toUiError(error: unknown, fallbackMessage: string): UiError {
  if (error instanceof ApiClientError) {
    return {
      message: error.payload.message || fallbackMessage,
      retryable: Boolean(error.payload.retryable ?? error.payload.details?.retryable),
    };
  }
  if (error instanceof Error && error.message.trim()) {
    return { message: error.message, retryable: true };
  }
  return {
    message: fallbackMessage,
    retryable: false,
  };
}

function normalizeQuery(query: string): string {
  return query.trim().toUpperCase();
}

function dedupeRecentSearches(items: SymbolSearchItem[]): SymbolSearchItem[] {
  const seen = new Set<string>();
  const deduped: SymbolSearchItem[] = [];
  for (const item of items) {
    const key = `${item.market}:${item.ticker}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(item);
    if (deduped.length === RECENT_SEARCH_LIMIT) {
      break;
    }
  }
  return deduped;
}

function safeLoadRecentSearches(): SymbolSearchItem[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(RECENT_SEARCH_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return dedupeRecentSearches(
      parsed.filter((item): item is SymbolSearchItem => {
        if (!item || typeof item !== "object") {
          return false;
        }
        const value = item as Partial<SymbolSearchItem>;
        return (
          typeof value.ticker === "string" &&
          typeof value.name === "string" &&
          (value.market === "KR" || value.market === "US")
        );
      }),
    );
  } catch {
    return [];
  }
}

function safeSaveRecentSearches(items: SymbolSearchItem[]): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(RECENT_SEARCH_STORAGE_KEY, JSON.stringify(items));
  } catch {
    return;
  }
}

function searchFallbackCatalog(query: string, market: "KR" | "US"): SymbolSearchItem[] {
  const normalized = normalizeQuery(query);
  return FALLBACK_SYMBOLS.filter((item) => {
    if (item.market !== market) {
      return false;
    }
    return item.ticker.includes(normalized) || item.name.toUpperCase().includes(normalized);
  });
}

export function WatchlistComposer({ client, onToast }: WatchlistComposerProps): JSX.Element {
  const [watchlistStatus, setWatchlistStatus] = useState<LoadStatus>("loading");
  const [watchlistItems, setWatchlistItems] = useState<WatchlistItem[]>([]);
  const [watchlistError, setWatchlistError] = useState<UiError | null>(null);

  const [market, setMarket] = useState<"KR" | "US">("US");
  const [query, setQuery] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolSearchItem | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  const [searchStatus, setSearchStatus] = useState<SearchStatus>("idle");
  const [searchResults, setSearchResults] = useState<SymbolSearchItem[]>([]);
  const [searchError, setSearchError] = useState<UiError | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [recentSearches, setRecentSearches] = useState<SymbolSearchItem[]>([]);

  const [isSubmitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<SubmitError | null>(null);

  const searchRequestId = useRef(0);
  const submitInFlightRef = useRef(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const submitButtonRef = useRef<HTMLButtonElement | null>(null);

  const listboxId = useId();
  const descriptionId = `${listboxId}-description`;

  const normalizedQuery = useMemo(() => query.trim(), [query]);
  const queryLengthError = useMemo(() => {
    if (!normalizedQuery) {
      return null;
    }
    if (normalizedQuery.length < MIN_QUERY_LENGTH) {
      return `검색어를 ${MIN_QUERY_LENGTH}자 이상 입력하세요.`;
    }
    if (normalizedQuery.length > MAX_QUERY_LENGTH) {
      return `검색어는 ${MAX_QUERY_LENGTH}자 이하로 입력하세요.`;
    }
    return null;
  }, [normalizedQuery]);

  const listVisible = !selectedSymbol && normalizedQuery.length >= MIN_QUERY_LENGTH;
  const activeDescendant =
    highlightedIndex >= 0 && searchResults[highlightedIndex]
      ? `${listboxId}-item-${highlightedIndex}`
      : undefined;
  const searchStatusMessage = useMemo(() => {
    if (!listVisible) {
      return "";
    }
    if (queryLengthError) {
      return queryLengthError;
    }
    if (searchStatus === "loading") {
      return "검색 결과를 불러오는 중입니다.";
    }
    if (searchStatus === "error") {
      return searchError?.message ?? "검색 결과를 불러오지 못했습니다.";
    }
    if (searchStatus === "success" && searchResults.length === 0) {
      return "검색 결과가 없습니다.";
    }
    if (searchStatus === "success" && searchResults.length > 0) {
      return `${searchResults.length}개의 검색 결과가 있습니다.`;
    }
    return "";
  }, [listVisible, queryLengthError, searchError, searchResults.length, searchStatus]);

  async function loadWatchlist(): Promise<void> {
    setWatchlistStatus("loading");
    setWatchlistError(null);
    try {
      const response = await client.listWatchlistItems();
      setWatchlistItems(response.items);
      setWatchlistStatus("success");
    } catch (error) {
      setWatchlistError(toUiError(error, "관심종목을 불러오지 못했습니다."));
      setWatchlistStatus("error");
    }
  }

  function rememberRecentSearch(item: SymbolSearchItem): void {
    setRecentSearches((previous) => {
      const next = dedupeRecentSearches([item, ...previous]);
      safeSaveRecentSearches(next);
      return next;
    });
  }

  function selectSymbol(item: SymbolSearchItem): void {
    setSelectedSymbol(item);
    setQuery(item.ticker);
    setSearchStatus("idle");
    setSearchError(null);
    setSearchResults([]);
    setHighlightedIndex(-1);
    setSelectionError(null);
    setSubmitError(null);
    rememberRecentSearch(item);
    submitButtonRef.current?.focus();
  }

  async function performSearch(
    nextQuery: string,
    nextMarket: "KR" | "US",
    options: { silentToast?: boolean } = {},
  ): Promise<SymbolSearchItem[]> {
    const normalized = nextQuery.trim();
    if (normalized.length < MIN_QUERY_LENGTH || normalized.length > MAX_QUERY_LENGTH) {
      setSearchStatus("idle");
      setSearchResults([]);
      setSearchError(null);
      setHighlightedIndex(-1);
      return [];
    }

    const requestId = searchRequestId.current + 1;
    searchRequestId.current = requestId;
    setSearchStatus("loading");
    setSearchError(null);

    try {
      const response = await client.searchSymbols({ query: normalized, market: nextMarket });
      if (requestId !== searchRequestId.current) {
        return [];
      }
      setSearchResults(response.items);
      setSearchStatus("success");
      setHighlightedIndex(response.items.length > 0 ? 0 : -1);
      return response.items;
    } catch (error) {
      const fallbackResults = searchFallbackCatalog(normalized, nextMarket);
      if (requestId !== searchRequestId.current) {
        return [];
      }
      if (fallbackResults.length > 0) {
        setSearchResults(fallbackResults);
        setSearchStatus("success");
        setHighlightedIndex(0);
        return fallbackResults;
      }

      const uiError = toUiError(error, "심볼 검색에 실패했습니다.");
      setSearchError(uiError);
      setSearchResults([]);
      setSearchStatus("error");
      setHighlightedIndex(-1);
      if (!options.silentToast) {
        onToast({ kind: "error", message: uiError.message });
      }
      return [];
    }
  }

  useEffect(() => {
    setRecentSearches(safeLoadRecentSearches());
    void loadWatchlist();
  }, []);

  useEffect(() => {
    if (selectedSymbol) {
      return;
    }
    if (queryLengthError || !normalizedQuery) {
      setSearchStatus("idle");
      setSearchError(null);
      setSearchResults([]);
      setHighlightedIndex(-1);
      return;
    }

    const timer = window.setTimeout(() => {
      void performSearch(normalizedQuery, market, { silentToast: true });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [market, normalizedQuery, queryLengthError, selectedSymbol]);

  function handleQueryKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    const hasOptions = listVisible && searchStatus === "success" && searchResults.length > 0;
    if (event.key === "ArrowDown" && hasOptions) {
      event.preventDefault();
      setHighlightedIndex((previous) => {
        if (previous < 0) {
          return 0;
        }
        return Math.min(previous + 1, searchResults.length - 1);
      });
      return;
    }

    if (event.key === "ArrowUp" && hasOptions) {
      event.preventDefault();
      setHighlightedIndex((previous) => Math.max(previous - 1, 0));
      return;
    }

    if (event.key === "Enter" && hasOptions && highlightedIndex >= 0 && searchResults[highlightedIndex]) {
      event.preventDefault();
      selectSymbol(searchResults[highlightedIndex]);
      return;
    }

    if (event.key === "Escape" && listVisible) {
      event.preventDefault();
      setSearchStatus("idle");
      setSearchError(null);
      setSearchResults([]);
      setHighlightedIndex(-1);
    }
  }

  async function resolveSubmitSymbol(): Promise<SymbolSearchItem | null> {
    if (selectedSymbol) {
      return selectedSymbol;
    }

    if (queryLengthError) {
      setSelectionError(queryLengthError);
      return null;
    }

    const normalized = normalizeQuery(query);
    if (!normalized) {
      setSelectionError("종목을 검색하고 결과에서 선택하세요.");
      return null;
    }

    const exact = searchResults.find((item) => item.market === market && item.ticker === normalized);
    if (exact) {
      setSelectedSymbol(exact);
      return exact;
    }

    const latest = await performSearch(normalized, market, { silentToast: true });
    const resolved = latest.find((item) => item.market === market && item.ticker === normalized);
    if (resolved) {
      setSelectedSymbol(resolved);
      return resolved;
    }

    setSelectionError("검색 결과에서 종목을 선택하세요.");
    return null;
  }

  async function submitCandidate(candidate: SymbolSearchItem): Promise<void> {
    if (submitInFlightRef.current) {
      return;
    }
    submitInFlightRef.current = true;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await client.createWatchlistItem({ symbol: candidate.ticker, market: candidate.market });
      setQuery("");
      setSelectedSymbol(null);
      setSelectionError(null);
      setSearchStatus("idle");
      setSearchError(null);
      setSearchResults([]);
      setHighlightedIndex(-1);
      rememberRecentSearch(candidate);
      await loadWatchlist();
      onToast({ kind: "success", message: "관심종목이 저장되었습니다." });
      inputRef.current?.focus();
    } catch (error) {
      const message = error instanceof ApiClientError ? error.payload.message : "관심종목 저장에 실패했습니다.";
      setSubmitError({ candidate, message });
      onToast({ kind: "error", message });
    } finally {
      submitInFlightRef.current = false;
      setSubmitting(false);
    }
  }

  async function handleAddWatchlistItem(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (isSubmitting || submitInFlightRef.current) {
      return;
    }
    setSelectionError(null);

    const candidate = await resolveSubmitSymbol();
    if (!candidate) {
      onToast({ kind: "error", message: "검색 결과에서 종목을 선택하세요." });
      return;
    }

    const duplicate = watchlistItems.some(
      (item) => item.market === candidate.market && item.symbol.toUpperCase() === candidate.ticker,
    );
    if (duplicate) {
      onToast({ kind: "error", message: "이미 등록된 관심종목입니다." });
      return;
    }

    await submitCandidate(candidate);
  }

  async function handleDeleteWatchlistItem(itemId: string): Promise<void> {
    setSubmitError(null);
    try {
      await client.deleteWatchlistItem(itemId);
      onToast({ kind: "success", message: "관심종목이 삭제되었습니다." });
      await loadWatchlist();
    } catch (error) {
      const message = error instanceof ApiClientError ? error.payload.message : "관심종목 삭제에 실패했습니다.";
      onToast({ kind: "error", message });
    }
  }

  return (
    <section
      data-testid="watchlist-composer"
      style={{ border: "1px solid #cbd5e1", borderRadius: 12, background: "#fff", padding: 16 }}
    >
      <h2 style={{ marginTop: 0 }}>관심종목</h2>
      <p
        role="status"
        aria-live="polite"
        style={{
          margin: "0 0 8px",
          minHeight: 18,
          color: "#475569",
          fontSize: 12,
        }}
      >
        {searchStatusMessage}
      </p>
      <form onSubmit={handleAddWatchlistItem} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ flex: 1, minWidth: 220 }}>
          <input
            ref={inputRef}
            aria-label="종목코드"
            role="combobox"
            aria-autocomplete="list"
            aria-controls={listboxId}
            aria-describedby={descriptionId}
            aria-expanded={listVisible}
            aria-activedescendant={activeDescendant}
            aria-invalid={Boolean(queryLengthError || selectionError)}
            value={query}
            onChange={(event) => {
              setQuery(event.currentTarget.value);
              setSelectedSymbol(null);
              setSelectionError(null);
              setSubmitError(null);
            }}
            onKeyDown={handleQueryKeyDown}
            placeholder="예: AAPL"
            style={{ width: "100%", border: "1px solid #cbd5e1", borderRadius: 8, padding: "10px 12px", outlineOffset: 2 }}
          />
          <p id={descriptionId} style={{ margin: "6px 0 0", color: "#64748b", fontSize: 12 }}>
            검색 결과에서 선택한 종목만 저장됩니다.
          </p>
        </div>
        <select
          aria-label="시장"
          value={market}
          onChange={(event) => {
            setMarket(event.currentTarget.value as "KR" | "US");
            setSelectedSymbol(null);
          }}
          style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: "10px 12px", outlineOffset: 2 }}
        >
          <option value="US">US</option>
          <option value="KR">KR</option>
        </select>
        <button ref={submitButtonRef} type="submit" disabled={isSubmitting}>
          {isSubmitting ? "저장 중..." : "추가"}
        </button>
      </form>

      {listVisible && queryLengthError ? <p role="alert">{queryLengthError}</p> : null}
      {listVisible && searchStatus === "loading" ? <p data-testid="watchlist-search-loading">검색 결과 로딩 중...</p> : null}
      {listVisible && searchStatus === "error" && searchError ? (
        <div role="alert" style={{ marginBottom: 8 }}>
          <p>{searchError.message}</p>
          {searchError.retryable ? (
            <button type="button" onClick={() => void performSearch(normalizedQuery, market)}>
              검색 다시 시도
            </button>
          ) : null}
        </div>
      ) : null}
      {listVisible && searchStatus === "success" && searchResults.length === 0 ? (
        <p data-testid="watchlist-search-empty">검색 결과가 없습니다.</p>
      ) : null}
      {listVisible && searchStatus === "success" && searchResults.length > 0 ? (
        <ul id={listboxId} role="listbox" style={{ margin: "0 0 12px", paddingLeft: 20, maxHeight: 180, overflowY: "auto" }}>
          {searchResults.map((item, index) => (
            <li
              key={`${item.market}-${item.ticker}`}
              id={`${listboxId}-item-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              style={{ marginBottom: 4 }}
            >
              <button
                type="button"
                onClick={() => selectSymbol(item)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  border: index === highlightedIndex ? "1px solid #2563eb" : "1px solid #cbd5e1",
                  borderRadius: 8,
                  background: index === highlightedIndex ? "#eff6ff" : "#fff",
                  padding: "8px 10px",
                }}
              >
                {item.market}:{item.ticker} · {item.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {recentSearches.length > 0 ? (
        <section aria-label="최근검색" style={{ marginBottom: 12 }}>
          <p style={{ margin: "0 0 6px", fontSize: 13, color: "#334155" }}>최근 검색</p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {recentSearches.map((item) => (
              <button
                key={`${item.market}-${item.ticker}`}
                type="button"
                onClick={() => {
                  setMarket(item.market);
                  selectSymbol(item);
                }}
                style={{ border: "1px solid #cbd5e1", borderRadius: 999, padding: "4px 10px", background: "#f8fafc" }}
              >
                최근 {item.market}:{item.ticker}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {selectionError ? <p role="alert">{selectionError}</p> : null}
      {submitError ? (
        <div role="alert" style={{ marginBottom: 8 }}>
          <p>{submitError.message}</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" onClick={() => void submitCandidate(submitError.candidate)} disabled={isSubmitting}>
              저장 다시 시도
            </button>
            <button
              type="button"
              onClick={() => {
                setSubmitError(null);
                inputRef.current?.focus();
              }}
              disabled={isSubmitting}
            >
              취소
            </button>
          </div>
        </div>
      ) : null}

      {watchlistStatus === "loading" ? <p data-testid="watchlist-loading">관심종목 로딩 중...</p> : null}
      {watchlistStatus === "error" && watchlistError ? (
        <div role="alert">
          <p>{watchlistError.message}</p>
          <button type="button" onClick={() => void loadWatchlist()}>
            목록 다시 시도
          </button>
        </div>
      ) : null}
      {watchlistStatus === "success" && watchlistItems.length === 0 ? (
        <p data-testid="watchlist-empty">등록된 관심종목이 없습니다.</p>
      ) : null}
      {watchlistStatus === "success" && watchlistItems.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {watchlistItems.map((item) => (
            <li key={item.id} style={{ marginBottom: 6 }}>
              {item.market}:{item.symbol}{" "}
              <button type="button" onClick={() => void handleDeleteWatchlistItem(item.id)}>
                삭제
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
