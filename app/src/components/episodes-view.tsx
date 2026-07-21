"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EpisodesTable } from "@/components/episodes-table";
import { OutcomeBadge } from "@/components/outcome-badge";
import { StatusBadge } from "@/components/status-badge";
import { api, type EqualWeightReinvestment } from "@/lib/api";
import {
  assessmentLabel,
  formatDays,
  formatDate,
  formatExcessLabel,
  formatHoldAfterFirstLoss,
  formatInr,
  formatPct,
  formatPp,
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
      label: "Avg buy price (₹) · reference only",
      value: formatPrice(episode.average_buy_price),
      sublabel: "Not used for loss triggers; those use the first buy price",
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
          ? "Market price was below the first buy price for 1+ year, then sold at profit"
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

      {episode.major_loss_window ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50/50 p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Portfolio during the major-loss window</h3>
          <p className="mt-2 text-sm text-stone-600">
            The stock stayed continuously below its first buy price from{" "}
            <span className="font-medium text-stone-800">
              {formatDate(episode.major_loss_window.start_date)}
            </span>{" "}
            to{" "}
            <span className="font-medium text-stone-800">
              {formatDate(episode.major_loss_window.end_date)}
            </span>
            — {formatYears(episode.major_loss_window.calendar_days / 365.25)} (
            {formatDays(episode.major_loss_window.calendar_days)}
            {episode.major_loss_window.trading_days !== null
              ? ` · ${episode.major_loss_window.trading_days.toLocaleString("en-IN")} trading days`
              : ""}
            ).
          </p>

          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <Metric
              label="Stock return during loss window (%)"
              value={formatPct(episode.major_loss_window.stock_return_pct)}
            />
            <Metric
              label="Whole equity portfolio return (%)"
              value={formatPct(episode.major_loss_window.portfolio_return_pct)}
            />
            <Metric
              label="BSE SmallCap return (%)"
              value={formatPct(episode.major_loss_window.smallcap_return_pct)}
            />
            <Metric
              label="Stock vs portfolio (percentage points)"
              value={formatPp(episode.major_loss_window.stock_vs_portfolio_pct)}
            />
            <Metric
              label="Stock vs BSE SmallCap (percentage points)"
              value={formatPp(episode.major_loss_window.stock_vs_smallcap_pct)}
            />
            <Metric
              label="Portfolio vs BSE SmallCap (percentage points)"
              value={formatPp(episode.major_loss_window.portfolio_vs_smallcap_pct)}
            />
            <Metric
              label="Stock price at window start (₹)"
              value={formatPrice(episode.major_loss_window.start_price)}
            />
            <Metric
              label="Stock price at window end (₹)"
              value={formatPrice(episode.major_loss_window.end_price)}
            />
          </div>

          {episode.major_loss_window.reinvestment_at_one_year_loss ? (
            <ReinvestmentScenario
              title="What if we sold when continuous loss reached one year?"
              description="This is the early-exit trigger: sell on the first trading day after 365 continuous calendar days below the first buy price, then divide the proceeds equally among every other equity held that day."
              scenario={episode.major_loss_window.reinvestment_at_one_year_loss}
            />
          ) : null}

          {episode.major_loss_window.reinvestment_after_loss ? (
            <ReinvestmentScenario
              title="What if we reinvested when the loss phase ended?"
              description="Sell when the continuous below-first-buy-price phase ends, then divide the proceeds equally among every other equity held that day."
              scenario={episode.major_loss_window.reinvestment_after_loss}
            />
          ) : (
            <p className="mt-5 text-sm text-stone-500">
              The loss phase ended on the actual sell date, so only the one-year early-exit
              scenario applies.
            </p>
          )}

          <p className="mt-5 text-xs text-stone-500">
            Provisional portfolio comparator: this uses total equity market value at the start and
            end of the same window and includes this stock. It is not a cash-flow-adjusted TWR and
            does not influence the exit verdict.
          </p>
        </section>
      ) : null}

      {episode.assessment_reason ? (
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Exit assessment</h3>
          <div className="mt-2">
            {episode.exit_assessment ? (
              <StatusBadge status={episode.exit_assessment} />
            ) : null}
          </div>
          <p className="mt-2 text-xs font-medium uppercase tracking-wide text-stone-500">
            {episode.assessment_confidence ?? "Unknown"} confidence
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-lg bg-stone-50 p-4">
              <p className="text-sm font-semibold">Ownership discipline</p>
              <p className="mt-2 text-sm text-stone-600">
                {episode.ownership_signals.length
                  ? episode.ownership_signals.map(assessmentLabel).join(", ")
                  : "No strong ownership-discipline signal"}
              </p>
            </div>
            <div className="rounded-lg bg-stone-50 p-4">
              <p className="text-sm font-semibold">One-year post-exit evidence</p>
              <p className="mt-2 text-sm text-stone-600">
                {episode.post_exit_signals.length
                  ? episode.post_exit_signals.map(assessmentLabel).join(", ")
                  : "Not yet available"}
              </p>
            </div>
          </div>
          <p className="mt-3 text-stone-600">{episode.assessment_reason}</p>
        </section>
      ) : null}

      <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold">Standardized post-exit horizons</h3>
        <p className="mt-2 text-sm text-stone-600">
          The final verdict uses 1-year stock and BSE SmallCap results. Three-year, five-year, and
          latest results are context only.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {episode.post_exit_horizons.map((horizon) => (
            <div key={horizon.horizon} className="rounded-lg border border-stone-200 p-4">
              <p className="font-semibold">{horizon.horizon}</p>
              {horizon.data_quality_status === "OK" ? (
                <>
                  <p className="mt-2 text-sm">
                    Stock <span className="font-medium">{formatPct(horizon.security_return_pct)}</span>
                  </p>
                  <p className="text-sm">
                    BSE SC <span className="font-medium">{formatPct(horizon.smallcap_return_pct)}</span>
                  </p>
                  <p className="text-sm">
                    Excess <span className="font-medium">{formatPp(horizon.excess_vs_smallcap_pct)}</span>
                  </p>
                  <p className="mt-2 text-xs text-stone-500">
                    Through {horizon.comparison_date ? formatDate(horizon.comparison_date) : "—"}
                  </p>
                </>
              ) : (
                <p className="mt-2 text-sm text-stone-500">
                  {horizon.data_quality_status === "NOT_YET_AVAILABLE"
                    ? "Not yet available"
                    : "Insufficient data"}
                </p>
              )}
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-stone-500">
          Portfolio figures in the API/export are provisional raw market-value context and are
          excluded from every signal and verdict.
        </p>
      </section>

      {postExit ? (
        <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Latest-date context</h3>
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
              label="Portfolio after exit (%) · provisional"
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
          <p className="mt-4 text-xs text-stone-500">
            Latest-date results do not determine the verdict. Portfolio results are provisional
            because they are not cash-flow-adjusted TWR.
          </p>
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

function ReinvestmentScenario({
  title,
  description,
  scenario,
}: {
  title: string;
  description: string;
  scenario: EqualWeightReinvestment;
}) {
  const advantage = scenario.reinvestment_advantage_pct;
  const absoluteAdvantage = advantage === null ? null : `${Math.abs(advantage).toFixed(1)} pp`;

  return (
    <div className="mt-6 rounded-lg border border-stone-200 bg-white p-5">
      <h4 className="font-semibold">{title}</h4>
      <p className="mt-2 text-sm text-stone-600">
        {description} Comparison runs from {formatDate(scenario.start_date)} until the stock&apos;s
        actual exit on {formatDate(scenario.end_date)}.
      </p>
      <p className="mt-2 text-xs font-medium text-amber-800">
        Provisional equal-weight what-if; this does not influence the exit verdict.
      </p>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Metric
          label="Continue holding this stock (%)"
          value={formatPct(scenario.stock_return_pct)}
        />
        <Metric
          label="Equal-weight other holdings (%)"
          value={formatPct(scenario.equal_weight_other_holdings_return_pct)}
        />
        <Metric
          label="Reinvestment advantage (percentage points)"
          value={formatPp(advantage)}
        />
        <Metric
          label="₹100 left in this stock became"
          value={formatPrice(scenario.value_if_stock_100)}
        />
        <Metric
          label="₹100 equally reinvested became"
          value={formatPrice(scenario.value_if_reinvested_100)}
        />
        <Metric
          label="Other holdings included"
          value={scenario.included_holdings.toLocaleString("en-IN")}
        />
      </div>

      <p className="mt-4 text-sm font-medium text-stone-800">
        {advantage === null
          ? "Not enough price coverage to judge reinvestment."
          : advantage > 0
            ? `Equal reinvestment was better by ${absoluteAdvantage}.`
            : advantage < 0
              ? `Continuing to hold the stock was better by ${absoluteAdvantage}.`
              : "Both choices produced the same return."}
      </p>
      {scenario.excluded_missing_prices > 0 ? (
        <p className="mt-2 text-xs text-amber-800">
          {scenario.excluded_missing_prices} other holdings were excluded because start/end prices
          were unavailable.
        </p>
      ) : null}
    </div>
  );
}
