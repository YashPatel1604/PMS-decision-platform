"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type ChangeRequest } from "@/lib/api";

export function DraftTray({
  draft,
  domain = "client_portfolio",
  onSubmitted,
}: {
  draft: ChangeRequest | null | undefined;
  domain?: string;
  onSubmitted?: () => void;
}) {
  const queryClient = useQueryClient();
  const submit = useMutation({
    mutationFn: async () => {
      if (!draft?.operations.length) throw new Error("No draft");
      if (domain === "pivot") return api.submitPivotSelection();
      const symbol = draft.operations[0]?.entity_id;
      if (!symbol) throw new Error("No symbol in draft");
      return api.submitClientPortfolioDraft(symbol);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["change-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
      onSubmitted?.();
    },
  });

  if (!draft || draft.status !== "draft" || !draft.operations.length) return null;

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold">Draft pending submission</p>
          <ul className="mt-1 space-y-0.5 text-amber-900">
            {draft.operations.map((op) => {
              const before = op.before_state?.qty;
              const after = op.after_state?.qty;
              return (
                <li key={op.change_operation_id}>
                  {op.entity_id}: {String(before ?? "—")} → {String(after ?? "—")}
                </li>
              );
            })}
          </ul>
        </div>
        <button
          type="button"
          onClick={() => submit.mutate()}
          disabled={submit.isPending}
          className="rounded-lg bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-800 disabled:opacity-60"
        >
          {submit.isPending ? "Submitting…" : "Submit for approval"}
        </button>
      </div>
      {submit.isError ? (
        <p className="mt-2 text-xs text-red-700">{(submit.error as Error).message}</p>
      ) : null}
    </div>
  );
}
