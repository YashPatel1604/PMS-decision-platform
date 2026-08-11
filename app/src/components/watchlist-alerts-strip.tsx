"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type WatchlistAlert } from "@/lib/api";
import { formatDate } from "@/lib/format";

function kindLabel(kind: string): string {
  return kind === "insider" ? "Insider" : "SAST";
}

function AlertCard({
  alert,
  onAcknowledge,
}: {
  alert: WatchlistAlert;
  onAcknowledge: (alertId: number) => void;
}) {
  return (
    <div
      className={`rounded-lg border px-4 py-3 ${
        alert.acknowledged
          ? "border-stone-200 bg-stone-50 opacity-70"
          : "border-amber-200 bg-amber-50/60"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-stone-900">
            <span className="mr-2 rounded-md bg-white px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-600">
              {kindLabel(alert.kind)}
            </span>
            {alert.company_name}
          </p>
          <p className="mt-1 text-xs text-stone-600">
            {alert.person_name} · {alert.transaction_type} · {formatDate(alert.disclosure_date)}
          </p>
          <p className="mt-1 text-xs text-stone-500">
            {alert.category}
            {alert.pct_pre != null && alert.pct_post != null
              ? ` · ${alert.pct_pre}% → ${alert.pct_post}%`
              : ""}
            {alert.market_cap_cr != null ? ` · MCap ₹${Math.round(alert.market_cap_cr)} Cr` : ""}
          </p>
        </div>
        {!alert.acknowledged ? (
          <button
            type="button"
            onClick={() => onAcknowledge(alert.alert_id)}
            className="rounded-md border border-stone-300 bg-white px-2 py-1 text-xs font-medium text-stone-700 hover:bg-stone-50"
          >
            Acknowledge
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function WatchlistAlertsStrip({ watchlistId }: { watchlistId: number }) {
  const queryClient = useQueryClient();

  const alertsQuery = useQuery({
    queryKey: ["watchlist-alerts", watchlistId],
    queryFn: () => api.listWatchlistAlerts(watchlistId, { refresh: true }),
    enabled: watchlistId > 0,
  });

  const pollMutation = useMutation({
    mutationFn: () => api.pollWatchlistAlerts(watchlistId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["watchlist-alerts", watchlistId] });
      await queryClient.invalidateQueries({ queryKey: ["watchlist-alerts-summary"] });
    },
  });

  const ackMutation = useMutation({
    mutationFn: (alertId: number) => api.acknowledgeWatchlistAlert(watchlistId, alertId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["watchlist-alerts", watchlistId] });
      await queryClient.invalidateQueries({ queryKey: ["watchlist-alerts-summary"] });
    },
  });

  const alerts = alertsQuery.data ?? [];
  const unacknowledged = alerts.filter((row) => !row.acknowledged);

  if (alertsQuery.isLoading) {
    return (
      <p className="text-sm text-stone-500">Checking promoter / insider alerts…</p>
    );
  }

  return (
    <div className="space-y-3 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-stone-900">Promoter & insider alerts</p>
          <p className="text-xs text-stone-500">
            SAST (Reg 29) and Insider Trading 2015 filtered to this watchlist.
          </p>
        </div>
        <button
          type="button"
          onClick={() => pollMutation.mutate()}
          disabled={pollMutation.isPending}
          className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-600 hover:bg-stone-50"
        >
          {pollMutation.isPending ? "Refreshing…" : "Refresh alerts"}
        </button>
      </div>

      {unacknowledged.length === 0 ? (
        <p className="text-sm text-stone-500">No new SAST or insider alerts for watchlist stocks.</p>
      ) : (
        <div className="space-y-2">
          {unacknowledged.map((alert) => (
            <AlertCard
              key={alert.alert_id}
              alert={alert}
              onAcknowledge={(id) => ackMutation.mutate(id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
