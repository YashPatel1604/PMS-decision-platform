"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function WatchlistHealthPanel({ watchlistId }: { watchlistId?: number }) {
  const globalQuery = useQuery({
    queryKey: ["watchlists-health"],
    queryFn: () => api.getWatchlistsHealth(),
    enabled: watchlistId == null,
  });

  const listQuery = useQuery({
    queryKey: ["watchlist-health", watchlistId],
    queryFn: () => api.getWatchlistHealth(watchlistId!),
    enabled: watchlistId != null,
  });

  const settingsQuery = useQuery({
    queryKey: ["watchlist-settings"],
    queryFn: () => api.getWatchlistSettings(),
  });

  if (globalQuery.isLoading || listQuery.isLoading) {
    return <p className="text-sm text-stone-500">Loading health…</p>;
  }

  const settings = settingsQuery.data;
  const row = watchlistId != null ? listQuery.data : null;
  const global = watchlistId == null ? globalQuery.data : null;

  return (
    <div className="space-y-4 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <div>
        <p className="text-sm font-semibold text-stone-900">Data quality</p>
        {settings ? (
          <p className="text-xs text-stone-500">
            Fundamentals provider: <span className="font-medium">{settings.fundamentals_provider}</span>
            {" · "}
            Available: {settings.available_providers.join(", ")}
          </p>
        ) : null}
      </div>

      {row ? (
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <Stat label="Members" value={row.member_count} />
          <Stat label="Resolved" value={row.resolved_count} warn={row.unresolved_count > 0} />
          <Stat label="Unresolved" value={row.unresolved_count} warn={row.unresolved_count > 0} />
          <Stat label="With fundamentals" value={row.with_fundamentals_count} />
          <Stat label="Missing fundamentals" value={row.missing_fundamentals_count} warn={row.missing_fundamentals_count > 0} />
          <Stat label="Stale fundamentals" value={row.stale_fundamentals_count} warn={row.stale_fundamentals_count > 0} />
          <Stat label="Open alerts" value={row.unacknowledged_alerts} warn={row.unacknowledged_alerts > 0} />
        </dl>
      ) : null}

      {global ? (
        <>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <Stat label="Watchlists" value={global.watchlist_count} />
            <Stat label="Total members" value={global.total_members} />
            <Stat label="Unresolved symbols" value={global.total_unresolved} warn={global.total_unresolved > 0} />
            <Stat label="Open alerts" value={global.total_unacknowledged_alerts} warn={global.total_unacknowledged_alerts > 0} />
            <Stat label="Missing fundamentals" value={global.total_missing_fundamentals} warn={global.total_missing_fundamentals > 0} />
            <Stat label="Stale fundamentals" value={global.total_stale_fundamentals} warn={global.total_stale_fundamentals > 0} />
          </dl>
          {global.watchlists.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="py-2 pr-4">List</th>
                    <th className="py-2 pr-4">Members</th>
                    <th className="py-2 pr-4">Unresolved</th>
                    <th className="py-2 pr-4">No fundamentals</th>
                    <th className="py-2">Alerts</th>
                  </tr>
                </thead>
                <tbody>
                  {global.watchlists.map((w) => (
                    <tr key={w.watchlist_id} className="border-t border-stone-100">
                      <td className="py-2 pr-4 font-medium">{w.name}</td>
                      <td className="py-2 pr-4 tabular-nums">{w.member_count}</td>
                      <td className="py-2 pr-4 tabular-nums">{w.unresolved_count}</td>
                      <td className="py-2 pr-4 tabular-nums">{w.missing_fundamentals_count}</td>
                      <td className="py-2 tabular-nums">{w.unacknowledged_alerts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function Stat({
  label,
  value,
  warn = false,
}: {
  label: string;
  value: number;
  warn?: boolean;
}) {
  return (
    <div className="rounded-lg border border-stone-100 bg-stone-50 px-3 py-2">
      <dt className="text-xs text-stone-500">{label}</dt>
      <dd className={`text-lg font-semibold tabular-nums ${warn ? "text-amber-800" : "text-stone-900"}`}>
        {value}
      </dd>
    </div>
  );
}
