"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/holdings", label: "Holdings" },
  { href: "/block-deals", label: "Block Deals" },
  { href: "/bulk-deals", label: "Bulk Deals" },
  { href: "/sast", label: "SAST" },
  { href: "/insider-trading", label: "Insider Trading" },
  { href: "/watchlists", label: "Watchlists", badgeKey: "watchlists" as const },
  { href: "/episodes", label: "Episodes" },
  { href: "/strategy/continuous-loss", label: "1-Year Loss Strategy" },
  { href: "/masters", label: "Masters" },
  { href: "/data", label: "Data" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);

  const alertsSummaryQuery = useQuery({
    queryKey: ["watchlist-alerts-summary"],
    queryFn: () => api.getWatchlistAlertsSummary(),
    refetchInterval: 5 * 60 * 1000,
  });

  const unacknowledgedAlerts = alertsSummaryQuery.data?.unacknowledged ?? 0;

  const refreshMutation = useMutation({
    mutationFn: () => api.refreshFromOnedrive(),
    onSuccess: (result) => {
      void queryClient.invalidateQueries();
      if (result.ok && result.reimport) {
        setMessage(
          `Synced ${result.sync.snapshot_count} snapshots · ${result.reimport.episodes} episodes`,
        );
      } else {
        setMessage(result.error ?? "Refresh finished with errors");
      }
    },
    onError: (err: Error) => setMessage(err.message),
  });

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
              PMS Decision Platform
            </p>
            <h1 className="text-lg font-semibold">Historical Decision Lab</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <nav className="flex flex-wrap gap-2">
              {links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="relative rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
                >
                  {link.label}
                  {link.badgeKey === "watchlists" && unacknowledgedAlerts > 0 ? (
                    <span className="ml-1.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                      {unacknowledgedAlerts > 99 ? "99+" : unacknowledgedAlerts}
                    </span>
                  ) : null}
                </Link>
              ))}
            </nav>
            <button
              type="button"
              disabled={refreshMutation.isPending}
              onClick={() => {
                setMessage(null);
                refreshMutation.mutate();
              }}
              title="Sync Research/OneDrive into data/raw and reimport"
              className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-semibold text-stone-800 hover:bg-stone-50 disabled:cursor-not-allowed disabled:text-stone-400"
            >
              {refreshMutation.isPending ? "Refreshing…" : "Refresh data"}
            </button>
          </div>
        </div>
        {message ? (
          <div className="border-t border-stone-100 bg-stone-50 px-6 py-2 text-xs text-stone-600">
            {message} · details on the Data page
          </div>
        ) : null}
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
