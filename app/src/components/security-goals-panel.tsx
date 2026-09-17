"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Compact open-goals strip for holdings / watchlist panels. */
export function SecurityGoalsPanel({ securityId }: { securityId: string }) {
  const queryClient = useQueryClient();
  const goalsQuery = useQuery({
    queryKey: ["research-goals", securityId, "open"],
    queryFn: () => api.listResearchGoals(securityId, { openOnly: true }),
    enabled: Boolean(securityId),
  });

  const doneMutation = useMutation({
    mutationFn: (goalId: number) => api.updateResearchGoal(goalId, { status: "done" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-goals"] });
    },
  });

  const goals = goalsQuery.data ?? [];

  return (
    <div className="space-y-2 border-t border-stone-100 pt-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">
          Research goals
        </p>
        <Link
          href={`/research?security_id=${encodeURIComponent(securityId)}`}
          className="text-[11px] text-emerald-800 underline-offset-2 hover:underline"
        >
          Manage
        </Link>
      </div>
      {goalsQuery.isLoading ? (
        <p className="text-xs text-stone-500">Loading…</p>
      ) : goals.length === 0 ? (
        <p className="text-xs text-stone-500">No open goals. Run a brief or paste a thesis on Research.</p>
      ) : (
        <ul className="space-y-2">
          {goals.map((goal) => (
            <li key={goal.goal_id} className="text-sm">
              <p className="text-stone-900">{goal.title}</p>
              <button
                type="button"
                className="mt-1 text-[11px] text-stone-600 underline-offset-2 hover:underline disabled:opacity-50"
                disabled={doneMutation.isPending}
                onClick={() => doneMutation.mutate(goal.goal_id)}
              >
                Mark done
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
