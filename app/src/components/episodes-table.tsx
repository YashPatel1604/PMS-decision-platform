"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { FormattedPct, FormattedValue } from "@/components/formatted-value";
import { OutcomeBadge } from "@/components/outcome-badge";
import { StatusBadge } from "@/components/status-badge";
import type { EpisodePerformance, PostExitHorizon } from "@/lib/api";
import {
  assessmentLabel,
  formatDate,
  formatHoldAfterFirstLoss,
  formatXirr,
  outcomeLabel,
} from "@/lib/format";

const OUTCOME_FILTERS = ["ALL", "PROFIT_STOCK", "LOSS_STOCK", "BREAKEVEN"] as const;

function OneYearPerformance({ horizons }: { horizons: PostExitHorizon[] }) {
  const row = horizons.find((horizon) => horizon.horizon === "1Y");
  if (!row || row.data_quality_status !== "OK") {
    return <span className="text-xs text-stone-500">Not yet available</span>;
  }
  return (
    <>
      <p className="text-xs">
        <span className="text-stone-500">Stock </span>
        <FormattedValue value={row.security_return_pct} kind="pct" />
      </p>
      <p className="text-xs">
        <span className="text-stone-500">BSE SC </span>
        <FormattedValue value={row.smallcap_return_pct} kind="pct" />
      </p>
      {row.excess_vs_smallcap_pct !== null ? (
        <p className="mt-1 text-xs">
          <FormattedPct value={row.excess_vs_smallcap_pct} suffix="stock vs BSE SC" />
        </p>
      ) : null}
    </>
  );
}

export function EpisodesTable({ episodes }: { episodes: EpisodePerformance[] }) {
  const [query, setQuery] = useState("");
  const [assessmentFilter, setAssessmentFilter] = useState("ALL");
  const [outcomeFilter, setOutcomeFilter] = useState<(typeof OUTCOME_FILTERS)[number]>("ALL");

  const filtered = useMemo(() => {
    return episodes.filter((episode) => {
      const matchesQuery =
        query.trim() === "" ||
        episode.portfolio_name.toLowerCase().includes(query.toLowerCase()) ||
        episode.security_id.toLowerCase().includes(query.toLowerCase());
      const matchesAssessment =
        assessmentFilter === "ALL" || episode.exit_assessment === assessmentFilter;
      const matchesOutcome =
        outcomeFilter === "ALL" || episode.exit_outcome === outcomeFilter;
      return matchesQuery && matchesAssessment && matchesOutcome;
    });
  }, [assessmentFilter, episodes, outcomeFilter, query]);

  const assessments = useMemo(() => {
    return Array.from(
      new Set(episodes.map((episode) => episode.exit_assessment).filter(Boolean)),
    ) as string[];
  }, [episodes]);

  const outcomeCounts = useMemo(() => {
    return episodes.reduce(
      (counts, episode) => {
        counts[episode.exit_outcome] = (counts[episode.exit_outcome] ?? 0) + 1;
        return counts;
      },
      {} as Record<string, number>,
    );
  }, [episodes]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm">
          <span className="font-semibold text-emerald-900">
            {outcomeCounts.PROFIT_STOCK ?? 0}
          </span>
          <span className="text-emerald-800"> profit stocks</span>
        </div>
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm">
          <span className="font-semibold text-red-900">{outcomeCounts.LOSS_STOCK ?? 0}</span>
          <span className="text-red-800"> loss stocks</span>
        </div>
      </div>

      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <input
          type="search"
          placeholder="Search company or security ID"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm xl:max-w-sm"
        />
        <div className="flex flex-col gap-3 sm:flex-row">
          <select
            value={outcomeFilter}
            onChange={(event) =>
              setOutcomeFilter(event.target.value as (typeof OUTCOME_FILTERS)[number])
            }
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
          >
            <option value="ALL">All outcomes</option>
            {OUTCOME_FILTERS.filter((value) => value !== "ALL").map((outcome) => (
              <option key={outcome} value={outcome}>
                {outcomeLabel(outcome)}
              </option>
            ))}
          </select>
          <select
            value={assessmentFilter}
            onChange={(event) => setAssessmentFilter(event.target.value)}
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
          >
            <option value="ALL">All assessments</option>
            {assessments.map((assessment) => (
              <option key={assessment} value={assessment}>
                {assessmentLabel(assessment)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-stone-600">
            <tr>
              <th className="px-4 py-3 font-medium">Company</th>
              <th className="px-4 py-3 font-medium">Outcome</th>
              <th className="px-4 py-3 font-medium">Exit date</th>
              <th className="px-4 py-3 font-medium">P&amp;L (₹)</th>
              <th className="px-4 py-3 font-medium">1 year after sell (%)</th>
              <th className="px-4 py-3 font-medium">Below first buy</th>
              <th className="px-4 py-3 font-medium">XIRR (% p.a.)</th>
              <th className="px-4 py-3 font-medium">Final verdict</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((episode) => (
              <tr key={episode.episode_id} className="border-b border-stone-100 align-top last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/episodes/${episode.episode_id}`}
                    className="font-medium text-emerald-800 hover:underline"
                  >
                    {episode.portfolio_name}
                  </Link>
                  <p className="text-xs text-stone-500">{episode.security_id}</p>
                </td>
                <td className="px-4 py-3">
                  <OutcomeBadge
                    outcome={episode.exit_outcome}
                    lossHoldPattern={episode.loss_hold_pattern}
                  />
                </td>
                <td className="px-4 py-3">{formatDate(episode.exit_date)}</td>
                <td className="px-4 py-3">
                  <FormattedValue value={episode.total_profit_loss} kind="pnl" />
                </td>
                <td className="px-4 py-3">
                  <OneYearPerformance horizons={episode.post_exit_horizons} />
                </td>
                <td className="max-w-xs px-4 py-3 text-xs text-stone-600">
                  {formatHoldAfterFirstLoss(
                    episode.exit_outcome,
                    episode.first_below_cost_date,
                    episode.calendar_days_held_after_first_loss,
                    episode.days_held_after_first_loss,
                    episode.loss_hold_pattern,
                  )}
                </td>
                <td className="px-4 py-3 tabular-nums">{formatXirr(episode.stock_xirr)}</td>
                <td className="px-4 py-3">
                  {episode.exit_assessment ? (
                    <StatusBadge status={episode.exit_assessment} />
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-stone-500">
        Showing {filtered.length} of {episodes.length} closed episodes. Verdicts use fixed
        one-year stock and BSE SmallCap evidence; portfolio comparisons are provisional and
        excluded from verdicts.
      </p>
    </div>
  );
}
