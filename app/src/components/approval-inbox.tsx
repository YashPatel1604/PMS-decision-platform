"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type ChangeRequest } from "@/lib/api";

function RequestCard({ req }: { req: ChangeRequest }) {
  const queryClient = useQueryClient();
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);

  const approve = useMutation({
    mutationFn: () => api.approveChangeRequest(req.change_request_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["change-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["charts-dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["pivot-dashboard"] });
    },
  });

  const reject = useMutation({
    mutationFn: () => api.rejectChangeRequest(req.change_request_id, rejectReason),
    onSuccess: () => {
      setShowReject(false);
      void queryClient.invalidateQueries({ queryKey: ["change-requests"] });
    },
  });

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-stone-900">{req.title}</p>
          <p className="text-xs text-stone-500">
            {req.proposer.display_name} · {req.submitted_at ? new Date(req.submitted_at).toLocaleString() : "—"}
          </p>
        </div>
        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
          {req.status}
        </span>
      </div>
      <ul className="mt-3 space-y-1 text-stone-700">
        {req.operations.map((op) => {
          const before = op.before_state?.qty;
          const after = op.after_state?.qty;
          return (
            <li key={op.change_operation_id}>
              {op.entity_id}: {String(before ?? "—")} → {String(after ?? "—")}
            </li>
          );
        })}
      </ul>
      {req.status === "submitted" ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => approve.mutate()}
            disabled={approve.isPending}
            className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
          >
            Approve
          </button>
          <button
            type="button"
            onClick={() => setShowReject((v) => !v)}
            className="rounded-lg border border-stone-300 px-3 py-1.5 text-xs font-semibold text-stone-700 hover:bg-stone-50"
          >
            Reject
          </button>
        </div>
      ) : null}
      {showReject ? (
        <div className="mt-3 space-y-2">
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Rejection reason (required)"
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
            rows={2}
          />
          <button
            type="button"
            onClick={() => reject.mutate()}
            disabled={reject.isPending || !rejectReason.trim()}
            className="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-800 disabled:opacity-60"
          >
            Confirm reject
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function ApprovalInbox() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["change-requests", "submitted"],
    queryFn: () => api.listChangeRequests("submitted"),
    refetchInterval: 15_000,
  });

  if (isLoading) return <p className="text-sm text-stone-500">Loading approvals…</p>;
  if (error) {
    return (
      <p className="text-sm text-stone-500">
        Approval workflow is not enabled on this server.
      </p>
    );
  }
  if (!data?.length) {
    return <p className="text-sm text-stone-500">No pending submissions.</p>;
  }

  return (
    <div className="space-y-3">
      {data.map((req) => (
        <RequestCard key={req.change_request_id} req={req} />
      ))}
    </div>
  );
}
