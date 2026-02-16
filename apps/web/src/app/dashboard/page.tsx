"use client";

import { useMemo } from "react";

import { AppShell } from "@/components/app-shell";
import { SettingsCenter } from "@/components/settings-center";
import { WatchlistEventsDashboard } from "@/components/watchlist-events-dashboard";
import { createBrowserClientBundle } from "@/lib/browser-client";

export default function DashboardPage(): JSX.Element {
  const bundle = useMemo(() => createBrowserClientBundle(), []);

  return (
    <AppShell client={bundle.client} session={bundle.session}>
      <div style={{ display: "grid", gap: 16 }}>
        <WatchlistEventsDashboard client={bundle.client} />
        <SettingsCenter client={bundle.client} />
      </div>
    </AppShell>
  );
}
