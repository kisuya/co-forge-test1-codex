import { createApiClient, type ApiClient } from "@/lib/api-client";
import { createBrowserSession, type AuthSession } from "@/lib/auth-session";

const DEFAULT_API_BASE_URL = "http://localhost:8000";

export type BrowserClientBundle = {
  client: ApiClient;
  session: AuthSession;
};

export function createBrowserClientBundle(onSessionExpired?: () => void): BrowserClientBundle {
  const session = createBrowserSession();
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;
  const client = createApiClient({
    baseUrl,
    session,
    onSessionExpired,
  });
  return { client, session };
}
