"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EpisodesTable } from "@/components/episodes-table";
import { OutcomeBadge } from "@/components/outcome-badge";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import {
  formatDays,
  formatDate,
  formatExcessLabel,
  formatHoldAfterFirstLoss,
  formatInr,
  formatPct,
  formatPnL,
  formatPrice,
  formatXirr,
  formatYears,
  outcomeLabel,
} from "@/lib/format";

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

  const metrics: Array<{ label: string; value: string; sublabel?: string }> = [
    { label: "Entry date", value: formatDate(episode.entry_date) },
    { label: "Exit date", value: formatDate(episode.exit_date) },
    { label: "Holding period", value: formatDays(episode.holding_days) },
    {
      label: "Holding period (years)",
      value: formatYears(episode.holding_days / 365.25),
    },
    { label: "Invested (₹)", value: formatInr(episode.total_invested) },
    { label: "P&L (₹)", value: formatPnL(episode.total_profit_loss) },
    { label: "Outcome", value: outcomeLabel(episode.exit_outcome) },
    {
      label: "Avg buy price (₹)",
      value: formatPrice(episode.average_buy_price),
      sublabel: "Volume-weighted average of buys",
    },
    {
      label: "Avg sell price (₹)",
      value: formatPrice(episode.average_sell_price),
      sublabel: "Volume-weighted average of sells",
    },
    { label: "Total return (%)", value: formatPct(episode.total_return_pct) },
    { label: "XIRR (% p.a.)", value: formatXirr(episode.stock_xirr) },
    { label: "Portfolio return (%)", value: formatPct(episode.portfolio_return_pct) },
    { label: "BSE SmallCap return (%)", value: formatPct(episode.smallcap_return_pct, 1, { signed: false }) },
    {
      label: "Excess vs BSE SmallCap (%)",
      value: formatExcessLabel(episode.excess_vs_smallcap),
    },
    {
      label: "Peak during hold (₹)",
      value: formatPrice(episode.peak_price_during_hold),
      sublabel: episode.peak_price_date
        ? `Highest price while we held · ${formatDate(episode.peak_price_date)}`
        : "Highest price while we held",
    },
    {
      label: "Exit price (₹)",
      value: formatPrice(episode.exit_adjusted_close),
    },
    {
      label: "Missed vs peak (%)",
      value:
        episode.missed_upside_vs_peak_pct !== null && episode.missed_upside_vs_peak_pct > 0
          ? `−${Math.abs(episode.missed_upside_vs_peak_pct).toFixed(1)}%`
          : "—",
      sublabel: "How far below the in-hold peak we sold",
    },
    {
      label: "Max drawdown (%)",
      value: episode.max_drawdown !== null ? formatPct(-Math.abs(episode.max_drawdown), 1, { signed: true }) : "—",
      sublabel: "From in-hold peak",
    },
    {
      label: "Held after final loss (loss stocks only)",
      value: formatHoldAfterFirstLoss(
        episode.exit_outcome,
        episode.first_below_cost_date,
        episode.calendar_days_held_after_first_loss,
        episode.days_held_after_first_loss,
        episode.loss_hold_pattern,
      ),
      sublabel:
        episode.loss_hold_pattern === "RECOVERED_AFTER_LONG_LOSS"
          ? "Market price was below average buy cost for 1+ year, then sold at profit"
          : episode.exit_outcome === "LOSS_STOCK" && episode.loss_hold_pattern
            ? "Pattern for future early-exit research"
            : undefined,
    },
    { label: "Days below cost (total)", value: formatDays(episode.days_below_cost) },
    {
      label: "Days underperforming benchmark",
      value: formatDays(episode.days_underperforming_benchmark),
    },
  ];

  return (
    <div className="space-y-8">
      <div>
        <Link href="/episodes" className="text-sm font-medium text-emerald-800 hover:underline">
          ← Back to episodes
        </Link>
        <h2 className="mt-4 text-3xl font-semibold tracking-tight">{episode.portfolio_name}</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <OutcomeBadge
            outcome={episode.exit_outcome}
            lossHoldPattern={episode.loss_hold_pattern}
          />
          {episode.exit_assessment ? <StatusBadge status={episode.exit_assessment} /> : null}
        </div>
        <p className="mt-1 text-stone-600">
          {episode.security_id} · Episode #{episode.episode_id}
        </p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {metrics.map(({ label, value, sublabel }) => (
          <div key={label} className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
            <p className="text-sm text-stone-500">{label}</p>
            <p className="mt-2 text-xl font-semibold tabular-nums">{value}</p>
            {sublabel ? <p className="mt-1 text-xs text-stone-500">{sublabel}</p> : null}
          </div>
        ))}
      </section>

      {episode.assessment_reason ? (
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Exit assessment</h3>
          <div className="mt-2">
            {episode.exit_assessment ? (
              <StatusBadge status={episode.exit_assessment} />
            ) : null}
          </div>
          <p className="mt-3 text-stone-600">{episode.assessment_reason}</p>
        </section>
      ) : null}

      {postExit ? (
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Post-exit performance</h3>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Metric
              label="Comparison date"
              value={postExit.comparison_date ? formatDate(postExit.comparison_date) : "—"}
            />
            <Metric
              label="Security return after exit (%)"
              value={formatPct(postExit.security_return_after_exit)}
            />
            <Metric
              label="Portfolio after exit (%)"
              value={formatPct(postExit.portfolio_return_after_exit, 1, { signed: false })}
            />
            <Metric
              label="BSE SmallCap after exit (%)"
              value={formatPct(postExit.smallcap_return_after_exit, 1, { signed: false })}
            />
            <Metric
              label="Excess vs BSE SmallCap (%)"
              value={formatExcessLabel(postExit.excess_vs_smallcap_after_exit)}
            />
            <Metric
              label="Excess vs portfolio (%)"
              value={formatExcessLabel(
                postExit.security_return_after_exit !== null &&
                  postExit.portfolio_return_after_exit !== null
                  ? postExit.security_return_after_exit - postExit.portfolio_return_after_exit
                  : null,
                "portfolio",
              )}
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
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}
