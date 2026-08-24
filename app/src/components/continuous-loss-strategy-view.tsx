"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  api,
  type ContinuousLossStrategy,
  type ContinuousLossStrategyEpisode,
} from "@/lib/api";
import {
  formatDate,
  formatDays,
  formatInr,
  formatPct,
  formatPnL,
  formatPp,
  formatPrice,
  toneClass,
  valueTone,
} from "@/lib/format";

const STATUS_FILTERS = ["ALL", "TRIGGERED", "NO_TRIGGER", "EXCLUDED"] as const;

function statusLabel(status: string): string {
  if (status === "TRIGGERED") return "Rule triggered";
  if (status === "NO_TRIGGER") return "No 1-year loss";
  return status.replace("EXCLUDED_", "").replaceAll("_", " ").toLowerCase();
}

function conclusionLabel(value: string): string {
  const labels: Record<string, string> = {
    BROADLY_POSITIVE: "The rule improved equal-₹100 outcomes",
    POSITIVE_BUT_OUTLIER_SENSITIVE: "Positive average, but an outlier matters",
    BROADLY_NEGATIVE: "The rule reduced equal-₹100 outcomes",
    NEGATIVE_BUT_OUTLIER_SENSITIVE: "Negative result, but an outlier matters",
    NEUTRAL: "The rule made no aggregate difference",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function StrategyLoading() {
  return (
    <div className="space-y-6" aria-label="Loading strategy backtest">
      <div className="h-28 animate-pulse rounded-xl bg-stone-200" />
      <div className="grid gap-4 md:grid-cols-3">
        <div className="h-24 animate-pulse rounded-lg bg-stone-200" />
        <div className="h-24 animate-pulse rounded-lg bg-stone-200" />
        <div className="h-24 animate-pulse rounded-lg bg-stone-200" />
      </div>
      <div className="h-80 animate-pulse rounded-xl bg-stone-200" />
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  return (
    <div className="min-w-0 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-stone-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${tone ? toneClass(tone) : ""}`}>
        {value}
      </p>
      {detail ? <p className="mt-1 text-sm text-stone-500">{detail}</p> : null}
    </div>
  );
}

function EqualCapitalSummary({ data }: { data: ContinuousLossStrategy }) {
  return (
    <div className="grid gap-6 sm:grid-cols-3 xl:grid-cols-4">
      <Metric
        label="Average ₹100 effect"
        value={formatPp(data.mean_return_advantage_pp)}
        detail="Equal importance for every triggered stock"
        tone={valueTone(data.mean_return_advantage_pp)}
      />
      <Metric
        label="Typical ₹100 effect"
        value={formatPp(data.median_return_advantage_pp)}
        detail="Median, reducing outlier influence"
        tone={valueTone(data.median_return_advantage_pp)}
      />
      <Metric
        label="Combined equal-capital result"
        value={formatPnL(data.equal_capital_net_difference)}
        detail={`${formatInr(data.equal_capital_start_value)} tested equally`}
        tone={valueTone(data.equal_capital_net_difference)}
      />
      <Metric
        label="Profit factor"
        value={data.profit_factor === null ? "—" : data.profit_factor.toFixed(2)}
        detail="Equal-capital gains divided by equal-capital losses"
      />
    </div>
  );
}

function OutlierAnalysis({ data }: { data: ContinuousLossStrategy }) {
  const ranked = [...data.episodes]
    .filter((row) => row.status === "TRIGGERED")
    .sort(
      (left, right) =>
        Math.abs(right.return_uplift_pct ?? 0) - Math.abs(left.return_uplift_pct ?? 0),
    );
  const mostInfluential = ranked[0];
  return (
    <section className="border-t border-stone-200 pt-8">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">
            Outlier test
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">Does one stock decide the answer?</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-stone-600">
            Contributions use each stock&apos;s absolute ₹100 return advantage. Leave-one-out
            recomputes the equal-stock average after removing one trigger.
          </p>
          <dl className="mt-6 divide-y divide-stone-200 border-y border-stone-200">
            <div className="flex items-center justify-between gap-4 py-3">
              <dt className="text-sm text-stone-600">Largest single contribution</dt>
              <dd className="font-semibold tabular-nums">
                {formatPct(data.top_episode_contribution_pct, 2, { signed: false })}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4 py-3">
              <dt className="text-sm text-stone-600">Top three contributions</dt>
              <dd className="font-semibold tabular-nums">
                {formatPct(data.top_three_contribution_pct, 2, { signed: false })}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4 py-3">
              <dt className="text-sm text-stone-600">Most influential removal</dt>
              <dd className="text-right font-semibold tabular-nums">
                {mostInfluential
                  ? `${mostInfluential.portfolio_name} · ${formatPp(
                      mostInfluential.leave_one_out_mean_return_advantage_pp,
                    )}${
                      mostInfluential.removal_flips_result
                        ? " · flips result"
                        : " · same conclusion"
                    }`
                  : "No triggered episode"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <caption className="sr-only">Largest episode contributions and leave-one-out results</caption>
            <thead className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="px-3 py-3 font-semibold">Stock</th>
                <th className="px-3 py-3 text-right font-semibold">₹100 advantage</th>
                <th className="px-3 py-3 text-right font-semibold">Share of movement</th>
                <th className="px-3 py-3 text-right font-semibold">Mean Δ without it</th>
              </tr>
            </thead>
            <tbody>
              {ranked.slice(0, 6).map((row) => (
                <tr key={row.episode_id} className="border-b border-stone-100">
                  <td className="px-3 py-3">
                    <Link
                      href={`/episodes/${row.episode_id}`}
                      className="font-medium text-emerald-800 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                    >
                      {row.portfolio_name}
                    </Link>
                  </td>
                  <td className={`px-3 py-3 text-right font-medium tabular-nums ${toneClass(valueTone(row.impact_rupees))}`}>
                    {formatPp(row.return_uplift_pct)}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {formatPct(row.absolute_contribution_share_pct, 2, { signed: false })}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <span
                      className={`font-medium tabular-nums ${toneClass(
                        valueTone(row.leave_one_out_mean_return_advantage_pp),
                      )}`}
                    >
                      {formatPp(row.leave_one_out_mean_return_advantage_pp)}
                    </span>
                    {row.removal_flips_result ? (
                      <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
                        Flips
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function EpisodeTable({ episodes }: { episodes: ContinuousLossStrategyEpisode[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("ALL");
  const filtered = useMemo(
    () =>
      episodes.filter((row) => {
        const searchMatch =
          !query.trim() ||
          row.portfolio_name.toLowerCase().includes(query.toLowerCase()) ||
          row.security_id.toLowerCase().includes(query.toLowerCase());
        const statusMatch =
          status === "ALL" ||
          row.status === status ||
          (status === "EXCLUDED" && row.status.startsWith("EXCLUDED_"));
        return searchMatch && statusMatch;
      }),
    [episodes, query, status],
  );

  return (
    <section className="border-t border-stone-200 pt-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Every closed episode</h2>
          <p className="mt-2 text-sm text-stone-600">
            Triggered rows contain the counterfactual values. No-trigger rows never completed a
            continuous 365-day loss below the first purchase price.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="sr-only" htmlFor="strategy-search">
            Search stocks
          </label>
          <input
            id="strategy-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search stocks"
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-200"
          />
          <label className="sr-only" htmlFor="strategy-status">
            Filter by trigger status
          </label>
          <select
            id="strategy-status"
            value={status}
            onChange={(event) => setStatus(event.target.value as (typeof STATUS_FILTERS)[number])}
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-200"
          >
            <option value="ALL">All episodes</option>
            <option value="TRIGGERED">Rule triggered</option>
            <option value="NO_TRIGGER">No trigger</option>
            <option value="EXCLUDED">Excluded</option>
          </select>
        </div>
      </div>

      <div className="mt-5 overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3 font-semibold">Stock</th>
              <th className="px-4 py-3 font-semibold">Trigger</th>
              <th className="px-4 py-3 text-right font-semibold">Time measured</th>
              <th className="px-4 py-3 text-right font-semibold">₹100 held became</th>
              <th className="px-4 py-3 text-right font-semibold">₹100 diversified became</th>
              <th className="px-4 py-3 text-right font-semibold">₹100 advantage</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.episode_id} className="border-b border-stone-100 align-top last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/episodes/${row.episode_id}`}
                    className="font-medium text-emerald-800 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                  >
                    {row.portfolio_name}
                  </Link>
                  <p className="text-xs text-stone-500">{row.security_id}</p>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${
                      row.status === "TRIGGERED"
                        ? "bg-amber-100 text-amber-900"
                        : row.status === "NO_TRIGGER"
                          ? "bg-stone-100 text-stone-700"
                          : "bg-red-50 text-red-800"
                    }`}
                  >
                    {statusLabel(row.status)}
                  </span>
                  {row.trigger_date ? (
                    <>
                      <p className="mt-2 text-xs text-stone-600">{formatDate(row.trigger_date)}</p>
                      <p className="text-xs text-stone-500">
                        First buy {formatPrice(row.initial_purchase_price)}
                      </p>
                    </>
                  ) : row.note ? (
                    <p className="mt-2 max-w-xs text-xs text-stone-500">{row.note}</p>
                  ) : null}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatDays(row.measurement_days)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatPrice(
                    row.stock_return_pct === null ? null : 100 * (1 + row.stock_return_pct / 100),
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatPrice(
                    row.diversified_return_pct === null
                      ? null
                      : 100 * (1 + row.diversified_return_pct / 100),
                  )}
                  {row.missing_price_holdings_count > 0 ? (
                    <p className="text-xs text-amber-800">
                      {row.missing_price_holdings_count} holding(s) excluded
                    </p>
                  ) : null}
                </td>
                <td
                  className={`px-4 py-3 text-right font-medium tabular-nums ${toneClass(
                    valueTone(row.return_uplift_pct),
                  )}`}
                >
                  {formatPp(row.return_uplift_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-stone-500">
            No episodes match this filter.
          </p>
        ) : null}
      </div>
      <p className="mt-3 text-sm text-stone-500">
        Showing {filtered.length} of {episodes.length} closed episodes.
      </p>
    </section>
  );
}

export function ContinuousLossStrategyView() {
  const query = useQuery({
    queryKey: ["continuous-loss-strategy"],
    queryFn: api.getContinuousLossStrategy,
    staleTime: 5 * 60 * 1000,
  });

  if (query.isLoading) return <StrategyLoading />;
  if (query.isError || !query.data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-900">
        <h2 className="font-semibold">The strategy backtest could not be calculated.</h2>
        <p className="mt-2 text-sm">Confirm the API and historical price data are available.</p>
      </div>
    );
  }

  const data = query.data;
  const impactTone = valueTone(data.mean_return_advantage_pp);
  return (
    <div className="space-y-10">
      <header className="max-w-4xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
          Strategy research
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Sell after one continuous year below the first buy price
        </h1>
        <p className="mt-3 max-w-3xl text-base leading-7 text-stone-600">
          This counterfactual sells at the trigger, diversifies equally into every other equity
          with measurable prices, and compares both choices through that stock&apos;s actual exit.
          Every triggered stock receives the same hypothetical ₹100.
        </p>
      </header>

      <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">
              Equal-₹100 strategy conclusion
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">
              {conclusionLabel(data.conclusion)}
            </h2>
            <p className="mt-3 text-sm leading-6 text-stone-600">{data.conclusion_text}</p>
          </div>
          <div className="lg:text-right">
            <p className="text-sm text-stone-500">Average effect per ₹100 decision</p>
            <p className={`mt-1 text-3xl font-semibold tabular-nums ${toneClass(impactTone)}`}>
              {formatPp(data.mean_return_advantage_pp)}
            </p>
            <p className="mt-1 font-medium tabular-nums text-stone-600">
              Median {formatPp(data.median_return_advantage_pp)}
            </p>
          </div>
        </div>

        <div className="mt-8 grid divide-y divide-stone-200 border-y border-stone-200 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <div className="sm:pr-6">
            <Metric
              label="Rule triggered"
              value={`${data.triggered_episodes} of ${data.closed_episodes}`}
              detail={`${formatPct(data.trigger_rate_pct, 2, { signed: false })} of closed episodes`}
            />
          </div>
          <div className="sm:px-6">
            <Metric
              label="Win / tie / loss"
              value={`${data.positive_episodes} of ${data.triggered_episodes}`}
              detail={`${formatPct(data.positive_episode_rate_pct, 2, { signed: false })} wins · ${
                data.tie_episode_rate_pct === null
                  ? "— ties"
                  : `${formatPct(data.tie_episode_rate_pct, 2, { signed: false })} ties`
              } · ${formatPct(
                (data.negative_episodes / data.triggered_episodes) * 100,
                2,
                { signed: false },
              )} losses`}
            />
          </div>
          <div className="sm:pl-6">
            <Metric
              label="Equal capital tested"
              value={formatInr(data.equal_capital_start_value)}
              detail={`₹100 × ${data.triggered_episodes} triggered stocks`}
            />
          </div>
        </div>

        <div className="mt-8">
          <EqualCapitalSummary data={data} />
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <Metric
              label="Leave-one-out mean range"
              value={
                data.loo_min_mean_return_advantage_pp === null ||
                data.loo_max_mean_return_advantage_pp === null
                  ? "—"
                  : `${formatPp(data.loo_min_mean_return_advantage_pp)} to ${formatPp(
                      data.loo_max_mean_return_advantage_pp,
                    )}`
              }
              detail="Min/max mean advantage after excluding each triggered stock"
            />
            <Metric
              label="LOO positive fraction"
              value={
                data.loo_positive_fraction_pct === null
                  ? "—"
                  : formatPct(data.loo_positive_fraction_pct, 2, { signed: false })
              }
              detail="Share of episodes where mean remains positive after removal"
            />
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="Average winner"
              value={formatPp(data.average_winner_pp)}
              detail="Mean uplift among winning episodes"
              tone="positive"
            />
            <Metric
              label="Average loser"
              value={formatPp(data.average_loser_pp)}
              detail="Mean uplift among losing episodes"
              tone="negative"
            />
            <Metric
              label="Payoff ratio"
              value={data.payoff_ratio === null ? "—" : data.payoff_ratio.toFixed(2)}
              detail="Average winner divided by average loser magnitude"
            />
            <Metric
              label="Historical weighted uplift"
              value={formatPct(data.historical_capital_weighted_uplift_pct)}
              detail="Secondary view using actual trigger capital sizes"
              tone={valueTone(data.historical_capital_weighted_uplift_pct)}
            />
          </div>
          <div className="mt-6 grid gap-4 border-t border-stone-200 pt-6 sm:grid-cols-2">
            <Metric
              label="Continue holding"
              value={formatInr(data.hold_equal_capital_end_value)}
              detail={`From ${formatInr(data.equal_capital_start_value)} equal starting capital`}
            />
            <Metric
              label="Sell and diversify"
              value={formatInr(data.diversified_equal_capital_end_value)}
              detail={`${formatPnL(data.equal_capital_net_difference)} versus holding`}
              tone={valueTone(data.equal_capital_net_difference)}
            />
          </div>
        </div>
      </section>

      <OutlierAnalysis data={data} />
      <EpisodeTable episodes={data.episodes} />

      <section className="border-t border-stone-200 pt-6">
        <h2 className="text-lg font-semibold">Methodology and limits</h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-stone-600">{data.methodology}</p>
        <ul className="mt-3 max-w-4xl list-disc space-y-1 pl-5 text-sm text-stone-500">
          <li>The threshold is the first transaction price adjusted for splits and corporate actions.</li>
          <li>
            Every triggered stock receives the same hypothetical ₹100; actual rupee allocations
            do not affect the conclusion.
          </li>
          <li>Each comparison ends on that stock&apos;s actual exit date.</li>
          <li>
            Equal-episode mean uplift is the primary metric; median, payoff asymmetry, and
            leave-one-out sensitivity are secondary checks.
          </li>
          <li>
            Holdings without measurable start/end prices are excluded from that episode&apos;s
            equal-weight basket and reported.
          </li>
          <li>Episodes are independent; diversified baskets are not rebalanced or triggered again.</li>
          <li>This is a historical counterfactual, not a forecast or an executable recommendation.</li>
        </ul>
      </section>
    </div>
  );
}
