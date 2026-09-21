"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api, type DailyEditCategory, type DailyEditReimportResult } from "@/lib/api";

function apiDetail(err: Error): string {
  try {
    const parsed = JSON.parse(err.message) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    /* plain text */
  }
  return err.message;
}

function deltaLine(result: DailyEditReimportResult | null | undefined): string {
  if (!result) return "";
  return ` +${result.added?.length ?? 0} / −${result.removed?.length ?? 0} symbols`;
}

export function DailyEditPanel({
  category,
  title,
}: {
  category: DailyEditCategory;
  title?: string;
}) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<DailyEditReimportResult | null>(null);
  const [updateQty, setUpdateQty] = useState(true);

  const statusQuery = useQuery({
    queryKey: ["daily-edit-status"],
    queryFn: () => api.getDailyEditStatus(),
  });

  const catStatus = statusQuery.data?.categories[category];

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploadDailyEdit(category, file),
    onSuccess: (result) => {
      setPreview(result.pending ?? null);
      setMessage(
        result.deduplicated
          ? `Same file on server.${result.pending ? " Review and confirm to apply." : ""}`
          : `Uploaded ${result.filename}. Review the preview, then confirm new numbers.`,
      );
      void queryClient.invalidateQueries({ queryKey: ["daily-edit-status"] });
    },
    onError: (err: Error) => setMessage(apiDetail(err)),
  });

  const previewMutation = useMutation({
    mutationFn: () =>
      api.reimportDailyEdit(category, { dryRun: true, updateQty, authoritative: true }),
    onSuccess: (result) => {
      setPreview(result);
      setMessage("Preview ready — confirm when the deltas look right.");
    },
    onError: (err: Error) => setMessage(apiDetail(err)),
  });

  const confirmMutation = useMutation({
    mutationFn: () =>
      api.reimportDailyEdit(category, { dryRun: false, updateQty, authoritative: true }),
    onSuccess: (result) => {
      setPreview(null);
      setMessage(`Confirmed new numbers.${deltaLine(result)}.`);
      void queryClient.invalidateQueries();
    },
    onError: (err: Error) => setMessage(apiDetail(err)),
  });

  const busy =
    uploadMutation.isPending || previewMutation.isPending || confirmMutation.isPending;

  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
      <h3 className="font-medium text-slate-800">{title ?? "DailyEdit cloud sync"}</h3>
      <p className="mt-1 text-slate-600">
        Upload stages a workbook. Live strategy numbers change only after you confirm.
      </p>
      {catStatus && (
        <p className="mt-2 text-slate-500">
          On server:{" "}
          {catStatus.on_disk ? catStatus.filename ?? "workbook present" : "no file yet"}
          {catStatus.uploaded_at ? ` · last upload ${catStatus.uploaded_at}` : ""}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadMutation.mutate(file);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          className="rounded bg-slate-800 px-3 py-1.5 text-white disabled:opacity-50"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          Upload .xlsx
        </button>
        {catStatus?.reimport_supported ? (
          <>
            <button
              type="button"
              className="rounded border border-slate-300 bg-white px-3 py-1.5 disabled:opacity-50"
              disabled={busy || !catStatus.on_disk}
              onClick={() => previewMutation.mutate()}
            >
              Preview
            </button>
            <button
              type="button"
              className="rounded border border-emerald-700 bg-emerald-700 px-3 py-1.5 font-medium text-white disabled:opacity-50"
              disabled={busy || !preview}
              onClick={() => confirmMutation.mutate()}
            >
              Confirm new numbers
            </button>
          </>
        ) : null}
      </div>
      {category === "client_portfolio" || category === "sca_llp" ? (
        <label className="mt-2 flex items-center gap-2 text-slate-600">
          <input
            type="checkbox"
            checked={updateQty}
            onChange={(e) => setUpdateQty(e.target.checked)}
          />
          Update qty from Excel when confirming
        </label>
      ) : null}
      {preview ? (
        <div className="mt-3 space-y-2">
          <p className="text-amber-900">
            Pending confirm{deltaLine(preview)}. Live numbers are unchanged until you confirm.
          </p>
          <pre className="overflow-x-auto rounded bg-white p-2 text-xs text-slate-700">
            {JSON.stringify(preview, null, 2)}
          </pre>
        </div>
      ) : null}
      {message ? <p className="mt-2 text-slate-700">{message}</p> : null}
    </section>
  );
}
