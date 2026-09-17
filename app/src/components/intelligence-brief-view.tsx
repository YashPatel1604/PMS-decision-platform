"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, type IntelligenceBrief, type PortfolioEventRow } from "@/lib/api";

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: unknown };
      if (typeof parsed.detail === "string") return parsed.detail;
    } catch {
      /* plain */
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Request failed";
}

function materialityClass(level: string): string {
  switch (level.toUpperCase()) {
    case "URGENT":
      return "text-red-800";
    case "REVIEW":
      return "text-amber-800";
    case "WATCH":
      return "text-sky-800";
    default:
      return "text-stone-600";
  }
}

function EventList({ title, rows }: { title: string; rows: PortfolioEventRow[] }) {
  return (
    <section className="space-y-3 border-t border-stone-200 pt-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg text-stone-900">{title}</h2>
        <span className="text-xs text-stone-500">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-stone-500">Nothing in this bucket.</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => (
            <li key={row.event_id} className="space-y-1 border-b border-stone-100 pb-3 last:border-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
                <span className={`font-medium ${materialityClass(row.materiality)}`}>
                  {row.materiality}
                </span>
                <span className="text-stone-900">
                  {row.company || row.security_id || "Unknown"}
                </span>
                {row.event_date ? (
                  <span className="text-xs text-stone-500">{row.event_date}</span>
                ) : null}
                {row.universe ? (
                  <span className="text-xs uppercase tracking-wide text-stone-400">
                    {row.universe}
                  </span>
                ) : null}
              </div>
              <p className="text-sm text-stone-700">{row.summary}</p>
              <p className="text-xs text-stone-500">{row.materiality_reason}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function IntelligenceBriefView() {
  const queryClient = useQueryClient();

  const briefQuery = useQuery({
    queryKey: ["intelligence-brief"],
    queryFn: () => api.getIntelligenceBrief(7),
  });

  const syncMutation = useMutation({
    mutationFn: () => api.syncIntelligenceInsiderEvents(14),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["intelligence-brief"] });
    },
  });

  const brief: IntelligenceBrief | undefined = briefQuery.data;
  const err =
    briefQuery.error != null
      ? errorMessage(briefQuery.error)
      : syncMutation.error != null
        ? errorMessage(syncMutation.error)
        : null;

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-8">
      <header className="space-y-3">
        <p className="text-sm uppercase tracking-[0.2em] text-stone-500">Intelligence</p>
        <h1 className="font-serif text-3xl text-stone-900 md:text-4xl">Morning brief</h1>
        <p className="max-w-2xl text-stone-600">
          Filtered surveillance for holdings and watchlist — material events only, with rule-based
          reasons. Sync insider disclosures into the event store, then review what needs attention.
          Research notes are optional: upload them on the Research page when you want search/briefs.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="border border-stone-800 px-4 py-2 text-sm text-stone-900 hover:bg-stone-900 hover:text-white disabled:opacity-50"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            {syncMutation.isPending ? "Syncing…" : "Sync insider events"}
          </button>
          <button
            type="button"
            className="border border-stone-300 px-4 py-2 text-sm text-stone-700 hover:border-stone-800 disabled:opacity-50"
            onClick={() => void briefQuery.refetch()}
            disabled={briefQuery.isFetching}
          >
            Refresh
          </button>
          {brief ? (
            <span className="text-xs text-stone-500">
              As of {brief.as_of} · {brief.lookback_days}d lookback
            </span>
          ) : null}
        </div>
        {syncMutation.data ? (
          <p className="text-xs text-stone-500">
            Insider sync: {syncMutation.data.inserted} new · {syncMutation.data.unchanged} unchanged
            · {syncMutation.data.days} disclosure days
          </p>
        ) : null}
        {err ? <p className="text-sm text-red-700">{err}</p> : null}
      </header>

      {briefQuery.isLoading ? (
        <p className="text-sm text-stone-600">Loading brief…</p>
      ) : brief ? (
        <>
          <EventList title="Needs attention" rows={brief.needs_attention} />
          <EventList title="Portfolio changes" rows={brief.portfolio_changes} />
          <EventList title="Watchlist changes" rows={brief.watchlist_changes} />
          <section className="space-y-3 border-t border-stone-200 pt-6">
            <h2 className="text-lg text-stone-900">Data problems</h2>
            {brief.data_problems.length === 0 ? (
              <p className="text-sm text-stone-500">No open data or thesis-conflict flags.</p>
            ) : (
              <ul className="space-y-2">
                {brief.data_problems.map((item, idx) => (
                  <li key={`${item.code}-${idx}`} className="text-sm text-stone-700">
                    <span className="font-medium text-stone-900">{item.code}</span>
                    {" — "}
                    {item.detail}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
