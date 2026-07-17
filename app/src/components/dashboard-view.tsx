"use client";

import { useQuery } from "@tanstack/react-query";

import { ExitInsightsTable } from "@/components/exit-insights-table";
import { RunAnalysisButton } from "@/components/run-analysis-button";
import { StatCard } from "@/components/stat-card";
import { api } from "@/lib/api";
import { assessmentLabel } from "@/lib/format";

const KEY_FLAGS = [
  "LATE_EXIT",
  "CAPITAL_ROTATION_MISSED",
  "GAVE_BACK_GAINS",
  "PREMATURE_EXIT",
  "GOOD_EXIT",
  "LOSS_AVOIDED",
] as const;

export function DashboardView() {
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: api.getSummary,
  });
  const insightsQuery = useQuery({
    queryKey: ["dashboard-exit-insights"],
    queryFn: api.getExitInsights,
  });

  if (summaryQuery.isLoading) {
    return <p className="text-stone-600">Loading dashboard…</p>;
  }

  if (summaryQuery.isError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-900">
        <p className="font-semibold">Could not reach the API.</p>
        <p className="mt-2 text-sm">
          Start the backend with <code className="rounded bg-red-100 px-1">make dev-api</code> on
          port 8000, then refresh.
        </p>
      </div>
    );
  }

  const summary = summaryQuery.data;
  if (!summary) {
    return null;
  }

  const problemFlags = KEY_FLAGS.filter((flag) => (summary.flag_counts[flag] ?? 0) > 0);

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 rounded-xl border border-stone-200 bg-white p-6 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Exit quality dashboard</h2>
          <p className="mt-2 max-w-2xl text-stone-600">
            Review late exits and post-exit comparisons — stock vs portfolio vs BSE SmallCap
            from sell date only (not from purchase).
          </p>
        </div>
        <RunAnalysisButton />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Closed episodes" value={summary.total_episodes} />
        <StatCard
          label="Late / rotation issues"
          value={
            (summary.flag_counts.LATE_EXIT ?? 0) +
            (summary.flag_counts.CAPITAL_ROTATION_MISSED ?? 0)
          }
          hint={`${summary.flag_counts.GAVE_BACK_GAINS ?? 0} gave back peak gains`}
          tone="warn"
        />
        <StatCard
          label="Premature exits"
          value={summary.flag_counts.PREMATURE_EXIT ?? 0}
          tone="warn"
        />
        <StatCard
          label="Good / loss avoided"
          value={
            (summary.flag_counts.GOOD_EXIT ?? 0) + (summary.flag_counts.LOSS_AVOIDED ?? 0)
          }
          tone="good"
        />
      </section>

      <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold">Exit signal counts</h3>
        <p className="mt-1 text-sm text-stone-600">
          A single sale can trigger multiple flags (e.g. held too long and sold below peak).
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {problemFlags.map((flag) => (
            <div
              key={flag}
              className="flex items-center justify-between rounded-lg border border-stone-200 px-4 py-3"
            >
              <span className="text-sm font-medium text-stone-700">{assessmentLabel(flag)}</span>
              <span className="text-lg font-semibold tabular-nums">
                {summary.flag_counts[flag] ?? 0}
              </span>
            </div>
          ))}
          {Object.entries(summary.assessment_counts)
            .filter(
              ([assessment]) =>
                assessment === "NEUTRAL_EXIT" || assessment === "INSUFFICIENT_DATA",
            )
            .map(([assessment, count]) => (
              <div
                key={assessment}
                className="flex items-center justify-between rounded-lg border border-stone-200 px-4 py-3"
              >
                <span className="text-sm font-medium text-stone-700">
                  {assessmentLabel(assessment)}
                </span>
                <span className="text-lg font-semibold tabular-nums">{count}</span>
              </div>
            ))}
        </div>
      </section>

      <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-lg font-semibold">Sold positions — live exit review</h3>
            <p className="mt-1 text-sm text-stone-600">
              Exit / peak / today in ₹ · since-sell returns in % · green = gain, red = loss
            </p>
          </div>
          {insightsQuery.isLoading ? (
            <p className="text-sm text-stone-500">Loading prices…</p>
          ) : null}
        </div>
        {insightsQuery.data ? (
          <div className="mt-4">
            <ExitInsightsTable rows={insightsQuery.data} />
          </div>
        ) : insightsQuery.isError ? (
          <p className="mt-4 text-sm text-amber-800">
            Could not load exit insights. Re-run analysis after migrating the database.
          </p>
        ) : null}
      </section>
    </div>
  );
}
