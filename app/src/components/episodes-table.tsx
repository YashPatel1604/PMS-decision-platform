"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import type { EpisodePerformance } from "@/lib/api";
import { assessmentLabel, formatDate, formatInr, formatPct, formatXirr } from "@/lib/format";

export function EpisodesTable({ episodes }: { episodes: EpisodePerformance[] }) {
  const [query, setQuery] = useState("");
  const [assessmentFilter, setAssessmentFilter] = useState("ALL");

  const filtered = useMemo(() => {
    return episodes.filter((episode) => {
      const matchesQuery =
        query.trim() === "" ||
        episode.portfolio_name.toLowerCase().includes(query.toLowerCase()) ||
        episode.security_id.toLowerCase().includes(query.toLowerCase());
      const matchesAssessment =
        assessmentFilter === "ALL" || episode.exit_assessment === assessmentFilter;
      return matchesQuery && matchesAssessment;
    });
  }, [assessmentFilter, episodes, query]);

  const assessments = useMemo(() => {
    return Array.from(
      new Set(episodes.map((episode) => episode.exit_assessment).filter(Boolean)),
    ) as string[];
  }, [episodes]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <input
          type="search"
          placeholder="Search company or security ID"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm sm:max-w-sm"
        />
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

      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-stone-600">
            <tr>
              <th className="px-4 py-3 font-medium">Company</th>
              <th className="px-4 py-3 font-medium">Exit</th>
              <th className="px-4 py-3 font-medium">P&amp;L</th>
              <th className="px-4 py-3 font-medium">Return</th>
              <th className="px-4 py-3 font-medium">XIRR</th>
              <th className="px-4 py-3 font-medium">vs BSE SmallCap</th>
              <th className="px-4 py-3 font-medium">Assessment</th>
              <th className="px-4 py-3 font-medium">Quality</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((episode) => (
              <tr key={episode.episode_id} className="border-b border-stone-100 last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/episodes/${episode.episode_id}`}
                    className="font-medium text-emerald-800 hover:underline"
                  >
                    {episode.portfolio_name}
                  </Link>
                  <p className="text-xs text-stone-500">{episode.security_id}</p>
                </td>
                <td className="px-4 py-3">{formatDate(episode.exit_date)}</td>
                <td className="px-4 py-3">{formatInr(episode.total_profit_loss)}</td>
                <td className="px-4 py-3">{formatPct(episode.total_return_pct)}</td>
                <td className="px-4 py-3">{formatXirr(episode.stock_xirr)}</td>
                <td className="px-4 py-3">{formatPct(episode.excess_vs_smallcap)}</td>
                <td className="px-4 py-3">
                  {episode.exit_assessment ? (
                    <StatusBadge status={episode.exit_assessment} />
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={episode.data_quality_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-stone-500">
        Showing {filtered.length} of {episodes.length} closed episodes
      </p>
    </div>
  );
}
