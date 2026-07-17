"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { FormattedPct, FormattedValue } from "@/components/formatted-value";
import { OutcomeBadge } from "@/components/outcome-badge";
import { StatusBadge } from "@/components/status-badge";
import type { ExitInsightRow } from "@/lib/api";
import {
  assessmentLabel,
  formatDate,
  formatExcessLabel,
  formatHoldAfterFirstLoss,
  formatPrice,
  formatYears,
} from "@/lib/format";

const FLAG_FILTERS = [
  "ALL",
  "LATE_EXIT",
  "CAPITAL_ROTATION_MISSED",
  "GAVE_BACK_GAINS",
  "PREMATURE_EXIT",
  "LEFT_STOCK_UPSIDE",
  "INDEX_OUTPERFORMED_HOLD",
  "PORTFOLIO_OUTPERFORMED_HOLD",
  "REDEPLOYMENT_LAG",
  "GOOD_EXIT",
  "LOSS_AVOIDED",
] as const;

function PostExitComparison({
  stock,
  portfolio,
  smallcap,
  excessVsSmallcap,
  excessVsPortfolio,
}: {
  stock: number | null;
  portfolio: number | null;
  smallcap: number | null;
  excessVsSmallcap: number | null;
  excessVsPortfolio: number | null;
}) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-stone-500">
        Since sell date (%)
      </p>
      <p className="mt-1 text-xs">
        <span className="text-stone-500">Stock </span>
        <FormattedValue value={stock} kind="pct" className="text-sm" />
      </p>
      <p className="text-xs">
        <span className="text-stone-500">Portfolio </span>
        <FormattedValue value={portfolio} kind="pct" className="text-sm" />
      </p>
      <p className="text-xs">
        <span className="text-stone-500">BSE SC </span>
        <FormattedValue value={smallcap} kind="pct" className="text-sm" />
      </p>
      {excessVsSmallcap !== null ? (
        <p className="mt-2 text-xs">
          <FormattedPct value={excessVsSmallcap} suffix="stock vs BSE SC" />
        </p>
      ) : null}
      {excessVsPortfolio !== null ? (
        <p className="text-xs">
          <FormattedPct value={excessVsPortfolio} suffix="stock vs portfolio" />
        </p>
      ) : null}
    </div>
  );
}

export function ExitInsightsTable({ rows }: { rows: ExitInsightRow[] }) {
  const [query, setQuery] = useState("");
  const [flagFilter, setFlagFilter] = useState<(typeof FLAG_FILTERS)[number]>("ALL");

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      const matchesQuery =
        query.trim() === "" ||
        row.portfolio_name.toLowerCase().includes(query.toLowerCase()) ||
        row.security_id.toLowerCase().includes(query.toLowerCase());
      const matchesFlag =
        flagFilter === "ALL" || row.assessment_flags.includes(flagFilter);
      return matchesQuery && matchesFlag;
    });
  }, [flagFilter, query, rows]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <input
          type="search"
          placeholder="Search sold positions"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm lg:max-w-sm"
        />
        <select
          value={flagFilter}
          onChange={(event) =>
            setFlagFilter(event.target.value as (typeof FLAG_FILTERS)[number])
          }
          className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
        >
          {FLAG_FILTERS.map((flag) => (
            <option key={flag} value={flag}>
              {flag === "ALL" ? "All exit signals" : assessmentLabel(flag)}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-stone-600">
            <tr>
              <th className="px-4 py-3 font-medium">Company</th>
              <th className="px-4 py-3 font-medium">Outcome</th>
              <th className="px-4 py-3 font-medium">Since sell (%)</th>
              <th className="px-4 py-3 font-medium">Below buy cost</th>
              <th className="px-4 py-3 font-medium">Prices (₹)</th>
              <th className="px-4 py-3 font-medium">Signals</th>
              <th className="px-4 py-3 font-medium">Analysis</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.episode_id} className="border-b border-stone-100 align-top last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/episodes/${row.episode_id}`}
                    className="font-medium text-emerald-800 hover:underline"
                  >
                    {row.portfolio_name}
                  </Link>
                  <p className="text-xs text-stone-500">{row.security_id}</p>
                  <p className="mt-1 text-xs text-stone-500">Sold {formatDate(row.exit_date)}</p>
                  <p className="text-xs text-stone-500">Held {formatYears(row.holding_years)}</p>
                  {row.comparison_date ? (
                    <p className="text-xs text-stone-500">
                      Compared to {formatDate(row.comparison_date)}
                    </p>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <OutcomeBadge
                    outcome={row.exit_outcome}
                    lossHoldPattern={row.loss_hold_pattern}
                  />
                  <p className="mt-2 text-xs">
                    <span className="text-stone-500">Total return </span>
                    <FormattedValue value={row.total_return_pct} kind="pct" />
                  </p>
                </td>
                <td className="px-4 py-3">
                  <PostExitComparison
                    stock={row.security_return_after_exit}
                    portfolio={row.portfolio_return_after_exit}
                    smallcap={row.smallcap_return_after_exit}
                    excessVsSmallcap={row.excess_vs_smallcap_after_exit}
                    excessVsPortfolio={row.excess_vs_portfolio_after_exit}
                  />
                </td>
                <td className="max-w-xs px-4 py-3 text-xs text-stone-600">
                  {formatHoldAfterFirstLoss(
                    row.exit_outcome,
                    row.first_below_cost_date,
                    row.calendar_days_held_after_first_loss,
                    row.days_held_after_first_loss,
                    row.loss_hold_pattern,
                  )}
                </td>
                <td className="px-4 py-3">
                  <p>
                    <span className="text-stone-500">Exit </span>
                    <span className="font-medium tabular-nums">{formatPrice(row.exit_price)}</span>
                  </p>
                  <p className="mt-1">
                    <span className="text-stone-500">Today </span>
                    <span className="tabular-nums">{formatPrice(row.current_price)}</span>
                  </p>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    <StatusBadge status={row.exit_assessment} />
                    {row.assessment_flags
                      .filter((flag) => flag !== row.exit_assessment)
                      .map((flag) => (
                        <StatusBadge key={flag} status={flag} />
                      ))}
                  </div>
                </td>
                <td className="max-w-sm px-4 py-3 text-xs text-stone-600">
                  {row.post_exit_summary ? (
                    <p className="font-medium text-stone-700">{row.post_exit_summary}</p>
                  ) : null}
                  <p className={row.post_exit_summary ? "mt-2" : ""}>{row.assessment_reason}</p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-stone-500">No exits match this filter.</p>
        ) : null}
      </div>
    </div>
  );
}
