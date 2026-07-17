"use client";

import { useQuery } from "@tanstack/react-query";

import { RunAnalysisButton } from "@/components/run-analysis-button";
import { StatCard } from "@/components/stat-card";
import { api } from "@/lib/api";
import { assessmentLabel } from "@/lib/format";

export function DashboardView() {
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: api.getSummary,
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

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 rounded-xl border border-stone-200 bg-white p-6 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Sell Since replacement</h2>
          <p className="mt-2 max-w-2xl text-stone-600">
            Review closed-episode performance, BSE SmallCap comparison, and post-exit sell
            assessments. Re-run analysis after data or transaction updates.
          </p>
        </div>
        <RunAnalysisButton />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Closed episodes" value={summary.total_episodes} />
        <StatCard
          label="Ownership metrics OK"
          value={summary.ownership_ok}
          hint={`${summary.ownership_insufficient} insufficient`}
          tone="good"
        />
        <StatCard
          label="Post-exit metrics OK"
          value={summary.post_exit_ok}
          hint={`${summary.post_exit_insufficient} insufficient`}
          tone="good"
        />
        <StatCard
          label="Premature exits flagged"
          value={summary.assessment_counts.PREMATURE_EXIT ?? 0}
          tone="warn"
        />
      </section>

      <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold">Exit assessments</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(summary.assessment_counts).map(([assessment, count]) => (
            <div
              key={assessment}
              className="flex items-center justify-between rounded-lg border border-stone-200 px-4 py-3"
            >
              <span className="text-sm font-medium text-stone-700">
                {assessmentLabel(assessment)}
              </span>
              <span className="text-lg font-semibold">{count}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
