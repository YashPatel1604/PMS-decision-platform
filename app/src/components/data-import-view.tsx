"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type OnedriveRefreshResult, type UploadBatch, type UploadKind } from "@/lib/api";

const KIND_OPTIONS: { value: UploadKind; label: string; help: string }[] = [
  {
    value: "transactions",
    label: "Transactions master",
    help: "Buy/sell and corporate-action workbook. Rebuilds episodes on commit.",
  },
  {
    value: "security_master",
    label: "Security master",
    help: "Security identifiers and portfolio names.",
  },
  {
    value: "portfolio_snapshots",
    label: "Portfolio snapshot",
    help: "One annual Portfolio_YYYY.xlsx workbook for quantity reconciliation.",
  },
];

function severityClass(severity: string): string {
  if (severity === "ERROR") return "bg-red-50 text-red-900 border-red-200";
  if (severity === "REVIEW") return "bg-amber-50 text-amber-900 border-amber-200";
  return "bg-stone-50 text-stone-700 border-stone-200";
}

export function DataImportView() {
  const [kind, setKind] = useState<UploadKind>("transactions");
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<UploadBatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshResult, setRefreshResult] = useState<OnedriveRefreshResult | null>(null);
  const queryClient = useQueryClient();

  const refreshMutation = useMutation({
    mutationFn: () => api.refreshFromOnedrive(),
    onSuccess: (result) => {
      setRefreshResult(result);
      setError(result.ok ? null : result.error);
      void queryClient.invalidateQueries();
    },
    onError: (err: Error) => {
      setRefreshResult(null);
      setError(err.message);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose an Excel file first");
      return api.uploadExcel(kind, file);
    },
    onSuccess: (result) => {
      setBatch(result);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      if (!batch) throw new Error("Upload a file first");
      return api.validateUpload(batch.batch_id);
    },
    onSuccess: (result) => {
      setBatch(result);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (!batch) throw new Error("Upload and validate first");
      return api.commitUpload(batch.batch_id);
    },
    onSuccess: (result) => {
      setBatch(result);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const busy =
    refreshMutation.isPending ||
    uploadMutation.isPending ||
    validateMutation.isPending ||
    commitMutation.isPending;

  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
          Data calibration
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Import Excel</h1>
        <p className="mt-3 text-base leading-7 text-stone-600">
          Research/OneDrive is not watched automatically. Use Refresh from Research when masters
          or portfolio snapshots change. Refresh now also imports market-data CSVs and recomputes
          episode analysis. You can still upload a single workbook below for calibration.
        </p>
      </header>

      <section className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-6 shadow-sm sm:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-2xl">
            <h2 className="text-xl font-semibold tracking-tight text-stone-900">
              Refresh from Research / OneDrive
            </h2>
            <p className="mt-2 text-sm leading-6 text-stone-700">
              Copies the latest securities, transactions, and{" "}
              <code className="rounded bg-white/80 px-1">Portfolio_*.xlsx</code> files from
              Research (with Final Master fallback) into{" "}
              <code className="rounded bg-white/80 px-1">data/raw</code>, reimports portfolio
              data, imports prices/dividends/benchmarks from the external data source, and
              recomputes episode analysis. Takes a few minutes.
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => refreshMutation.mutate()}
            className="shrink-0 rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-emerald-200"
          >
            {refreshMutation.isPending ? "Refreshing…" : "Refresh data"}
          </button>
        </div>
        {refreshResult ? (
          <div
            className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
              refreshResult.ok
                ? "border-emerald-300 bg-white text-emerald-950"
                : "border-red-200 bg-red-50 text-red-950"
            }`}
          >
            {refreshResult.ok ? (
              <p className="font-semibold">Refresh complete</p>
            ) : (
              <p className="font-semibold">{refreshResult.error ?? "Refresh failed"}</p>
            )}
            <p className="mt-1">
              Synced {refreshResult.sync.snapshot_count} snapshot workbook(s)
              {refreshResult.sync.research_dir
                ? ` from ${refreshResult.sync.research_dir}`
                : ""}
              .
            </p>
            {refreshResult.reimport ? (
              <p className="mt-1">
                Reimport: {refreshResult.reimport.securities_inserted} securities ·{" "}
                {refreshResult.reimport.equity_txns_inserted} equity txns ·{" "}
                {refreshResult.reimport.episodes} episodes ·{" "}
                {refreshResult.reimport.snapshots_inserted} snapshot rows
                {refreshResult.reimport.validation_errors
                  ? ` · ${refreshResult.reimport.validation_errors} validation errors`
                  : ""}
              </p>
            ) : null}
            {refreshResult.market_data ? (
              <p className="mt-1">
                Market data ({refreshResult.market_data.used_seed_fallback ? "seed fallback" : "OneDrive path"}
                ): prices +{refreshResult.market_data.prices_inserted} ({refreshResult.market_data.prices_skipped} unchanged) ·{" "}
                benchmarks +{refreshResult.market_data.benchmarks_inserted} · dividends +{refreshResult.market_data.dividends_inserted}
                {refreshResult.market_data.missing_files.length
                  ? ` · missing ${refreshResult.market_data.missing_files.join(", ")}`
                  : ""}
                .
              </p>
            ) : null}
            {refreshResult.analysis ? (
              <p className="mt-1">
                Analysis: ownership OK {refreshResult.analysis.ownership_ok} / insufficient{" "}
                {refreshResult.analysis.ownership_insufficient} · post-exit OK{" "}
                {refreshResult.analysis.post_exit_ok} / insufficient{" "}
                {refreshResult.analysis.post_exit_insufficient}.
              </p>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
        <h2 className="text-xl font-semibold tracking-tight">Upload a single workbook</h2>
        <p className="mt-2 text-sm text-stone-600">
          Use this for one-off calibration. Prefer Refresh above when Research already has the
          updated files.
        </p>
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <div className="space-y-5">
            <fieldset className="space-y-3">
              <legend className="text-sm font-semibold text-stone-800">Data kind</legend>
              {KIND_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className={`flex cursor-pointer gap-3 rounded-xl border p-3 ${
                    kind === option.value
                      ? "border-emerald-600 bg-emerald-50"
                      : "border-stone-200 bg-white"
                  }`}
                >
                  <input
                    type="radio"
                    name="upload-kind"
                    value={option.value}
                    checked={kind === option.value}
                    onChange={() => setKind(option.value)}
                    className="mt-1"
                  />
                  <span>
                    <span className="block font-medium text-stone-900">{option.label}</span>
                    <span className="mt-1 block text-sm text-stone-600">{option.help}</span>
                  </span>
                </label>
              ))}
            </fieldset>

            <label className="block text-sm font-semibold text-stone-800">
              Excel file
              <input
                type="file"
                accept=".xlsx,.xlsm"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="mt-2 block w-full text-sm text-stone-600"
              />
            </label>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                disabled={!file || busy}
                onClick={() => uploadMutation.mutate()}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-stone-300"
              >
                {uploadMutation.isPending ? "Uploading…" : "1. Upload"}
              </button>
              <button
                type="button"
                disabled={!batch || busy}
                onClick={() => validateMutation.mutate()}
                className="rounded-lg border border-stone-300 bg-white px-4 py-2 text-sm font-semibold text-stone-800 disabled:cursor-not-allowed disabled:text-stone-400"
              >
                {validateMutation.isPending ? "Checking…" : "2. Check & calibrate"}
              </button>
              <button
                type="button"
                disabled={!batch?.can_commit || busy || batch.status === "committed"}
                onClick={() => commitMutation.mutate()}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-emerald-200"
              >
                {commitMutation.isPending ? "Committing…" : "3. Commit to system"}
              </button>
            </div>

            {error ? (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
                {error}
              </p>
            ) : null}
          </div>

          <div className="rounded-xl border border-stone-200 bg-stone-50 p-5">
            <h2 className="text-lg font-semibold">Batch status</h2>
            {!batch ? (
              <p className="mt-3 text-sm text-stone-600">
                No upload yet. Choose a workbook and run the three steps in order.
              </p>
            ) : (
              <div className="mt-4 space-y-3 text-sm">
                <p>
                  <span className="text-stone-500">Batch</span>{" "}
                  <span className="font-semibold tabular-nums">#{batch.batch_id}</span>
                </p>
                <p>
                  <span className="text-stone-500">Status</span>{" "}
                  <span className="font-semibold">{batch.status}</span>
                </p>
                <p>
                  <span className="text-stone-500">Issues</span>{" "}
                  <span className="font-semibold">
                    {batch.error_count} errors · {batch.warning_count} warnings ·{" "}
                    {batch.review_count} review
                  </span>
                </p>
                {batch.notes ? <p className="text-stone-600">{batch.notes}</p> : null}
                {batch.episode_summary ? (
                  <p className="text-stone-600">
                    Episodes after commit: {batch.episode_summary.episodes} total (
                    {batch.episode_summary.open} open / {batch.episode_summary.closed} closed)
                  </p>
                ) : null}
                {!batch.can_commit && batch.error_count > 0 ? (
                  <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-900">
                    Commit is blocked until every ERROR is resolved.
                  </p>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </section>

      {batch && batch.issues.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-2xl font-semibold tracking-tight">Check results</h2>
          <ul className="space-y-2">
            {batch.issues.map((issue, index) => (
              <li
                key={`${issue.code}-${index}`}
                className={`rounded-xl border px-4 py-3 text-sm ${severityClass(issue.severity)}`}
              >
                <p className="font-semibold">
                  {issue.severity} · {issue.code}
                </p>
                <p className="mt-1">{issue.message}</p>
                {issue.security_id || issue.event_date ? (
                  <p className="mt-1 opacity-80">
                    {[issue.security_id, issue.event_date].filter(Boolean).join(" · ")}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="border-t border-stone-200 pt-6 text-sm text-stone-500">
        <h2 className="text-lg font-semibold text-stone-800">Refresh scope</h2>
        <p className="mt-2 max-w-3xl leading-6">
          Refresh handles both portfolio imports and market-data/analysis rebuild. For best
          results on Windows Docker, set both <code className="rounded bg-stone-100 px-1">RESEARCH_DIR</code> and{" "}
          <code className="rounded bg-stone-100 px-1">ONEDRIVE_EXTERNAL_DATA_DIR</code> in
          <code className="rounded bg-stone-100 px-1">.env</code> so the app prefers OneDrive
          data over bundled seed fallbacks.
        </p>
      </section>
    </div>
  );
}
