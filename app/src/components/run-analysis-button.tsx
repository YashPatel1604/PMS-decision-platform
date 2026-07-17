"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/lib/api";

export function RunAnalysisButton() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: api.runAnalysis,
    onSuccess: (result) => {
      setMessage(
        `Done: ${result.ownership_ok} ownership OK, ${result.post_exit_ok} post-exit OK`,
      );
      void queryClient.invalidateQueries();
    },
    onError: (error: Error) => {
      setMessage(error.message);
    },
  });

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {mutation.isPending ? "Running analysis…" : "Re-run episode analysis"}
      </button>
      {message ? <p className="text-sm text-stone-600">{message}</p> : null}
      {mutation.isPending ? (
        <p className="text-sm text-stone-500">This can take about 2 minutes on full history.</p>
      ) : null}
    </div>
  );
}
