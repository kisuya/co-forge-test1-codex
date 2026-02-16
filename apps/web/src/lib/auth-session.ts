export type AuthState = {
  userId: string;
  accessToken: string;
};

export type AuthSession = {
  get: () => AuthState | null;
  set: (state: AuthState) => void;
  clear: () => void;
};

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const SESSION_KEY = "oh-my-stock.auth.session";

function parseState(raw: string | null): AuthState | null {
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<AuthState>;
    if (typeof parsed.userId !== "string" || typeof parsed.accessToken !== "string") {
      return null;
    }
    return {
      userId: parsed.userId,
      accessToken: parsed.accessToken,
    };
  } catch {
    return null;
  }
}

export function createStorageBackedSession(storage: StorageLike): AuthSession {
  return {
    get: () => parseState(storage.getItem(SESSION_KEY)),
    set: (state) => {
      storage.setItem(SESSION_KEY, JSON.stringify(state));
    },
    clear: () => {
      storage.removeItem(SESSION_KEY);
    },
  };
}

export function createBrowserSession(): AuthSession {
  if (typeof window === "undefined" || !window.localStorage) {
    return createMemorySession();
  }
  return createStorageBackedSession(window.localStorage);
}

export function createMemorySession(initialState: AuthState | null = null): AuthSession {
  let state = initialState;
  return {
    get: () => state,
    set: (nextState) => {
      state = nextState;
    },
    clear: () => {
      state = null;
    },
  };
}
