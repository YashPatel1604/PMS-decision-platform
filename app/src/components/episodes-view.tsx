"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EpisodesTable } from "@/components/episodes-table";
import { api } from "@/lib/api";

export function EpisodesView() {
  const episodesQuery = useQuery({
    queryKey: ["episodes"],
    queryFn: api.listEpisodes,
  });

  if (episodesQuery.isLoading) {
    return <p className="text-stone-600">Loading episodes…</p>;
  }

  if (episodesQuery.isError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-900">
        <p className="font-semibold">Could not load episodes.</p>
        <p className="mt-2 text-sm">Ensure the API is running and episode analysis has been run.</p>
      </div>
    );
  }

  if (!episodesQuery.data) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Closed episodes</h2>
        <p className="mt-2 text-stone-600">
          Click a row to inspect ownership-period and post-exit metrics for one investment episode.
        </p>
      </div>
      <EpisodesTable episodes={episodesQuery.data} />
    </div>
  );
}

export function EpisodeDetailView({ episodeId }: { episodeId: number }) {
  const episodeQuery = useQuery({
    queryKey: ["episode", episodeId],
    queryFn: () => api.getEpisode(episodeId),
  });
  const postExitQuery = useQuery({
    queryKey: ["post-exit", episodeId],
    queryFn: () => api.getPostExit(episodeId),
    retry: false,
  });

  if (episodeQuery.isLoading) {
    return <p className="text-stone-600">Loading episode…</p>;
  }

  if (episodeQuery.isError || !episodeQuery.data) {
    return (
      <div className="space-y-4">
        <Link href="/episodes" className="text-sm font-medium text-emerald-800 hover:underline">
          ← Back to episodes
        </Link>
        <p className="text-red-700">Episode not found.</p>
      </div>
    );
  }

  const episode = episodeQuery.data;
  const postExit = postExitQuery.data;

  const metrics = [
    ["Entry", episode.entry_date],
    ["Exit", episode.exit_date],
    ["Holding days", String(episode.holding_days)],
    ["Invested", episode.total_invested.toFixed(0)],
    ["P&L", episode.total_profit_loss.toFixed(0)],
    ["Total return", episode.total_return_pct?.toFixed(1) ?? "—"],
    ["XIRR", episode.stock_xirr ? `${(episode.stock_xirr * 100).toFixed(1)}%` : "—"],
    ["Portfolio return", episode.portfolio_return_pct?.toFixed(1) ?? "—"],
    ["BSE SmallCap return", episode.smallcap_return_pct?.toFixed(1) ?? "—"],
    ["Excess vs BSE SmallCap", episode.excess_vs_smallcap?.toFixed(1) ?? "—"],
    ["Max drawdown", episode.max_drawdown?.toFixed(1) ?? "—"],
    ["Days below cost", episode.days_below_cost ?? "—"],
    ["Days underperforming benchmark", episode.days_underperforming_benchmark ?? "—"],
  ];

  return (
    <div className="space-y-8">
      <div>
        <Link href="/episodes" className="text-sm font-medium text-emerald-800 hover:underline">
          ← Back to episodes
        </Link>
        <h2 className="mt-4 text-3xl font-semibold tracking-tight">{episode.portfolio_name}</h2>
        <p className="mt-1 text-stone-600">
          {episode.security_id} · Episode #{episode.episode_id}
        </p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
            <p className="text-sm text-stone-500">{label}</p>
            <p className="mt-2 text-xl font-semibold">{value}</p>
          </div>
        ))}
      </section>

      {episode.assessment_reason ? (
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Exit assessment</h3>
          <p className="mt-2 text-sm font-medium text-stone-700">
            {episode.exit_assessment?.replaceAll("_", " ")}
          </p>
          <p className="mt-2 text-stone-600">{episode.assessment_reason}</p>
        </section>
      ) : null}

      {postExit ? (
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Post-exit performance</h3>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Metric label="Comparison date" value={postExit.comparison_date ?? "—"} />
            <Metric
              label="Security return after exit"
              value={
                postExit.security_return_after_exit !== null
                  ? `${postExit.security_return_after_exit.toFixed(1)}%`
                  : "—"
              }
            />
            <Metric
              label="BSE SmallCap after exit"
              value={
                postExit.smallcap_return_after_exit !== null
                  ? `${postExit.smallcap_return_after_exit.toFixed(1)}%`
                  : "—"
              }
            />
            <Metric
              label="Excess vs BSE SmallCap"
              value={
                postExit.excess_vs_smallcap_after_exit !== null
                  ? `${postExit.excess_vs_smallcap_after_exit.toFixed(1)}%`
                  : "—"
              }
            />
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-stone-500">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}
