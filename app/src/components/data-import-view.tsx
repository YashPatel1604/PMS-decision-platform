"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type OnedriveRefreshResult,
  type StagedImportRun,
  type UploadBatch,
  type UploadKind,
} from "@/lib/api";
import { DailyEditPanel } from "@/components/daily-edit-panel";

const DAILY_EDIT_PANELS: { category: "client_portfolio" | "charts" | "sca_llp" | "pivot_points"; title: string }[] = [
  { category: "client_portfolio", title: "Client Portfolio (PMS_ClientPortfolio.xlsx)" },
  { category: "charts", title: "Charts (Charts.xlsx)" },
  { category: "sca_llp", title: "SCA LLP" },
  { category: "pivot_points", title: "Pivot Points" },
];

const KIND_OPTIONS: { value: UploadKind; label: string; help: string }[] = [
  {
    value: "transactions",
    label: "Transactions master",
    help: "Buy/sell and corporate-action workbook. Rebuilds episodes on apply.",
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

function issueSeverityClass(severity: string): string {
  const upper = severity.toUpperCase();
  if (upper === "ERROR") return "bg-red-50 text-red-900 border-red-200";
  if (upper === "REVIEW") return "bg-amber-50 text-amber-900 border-amber-200";
  return "bg-stone-50 text-stone-700 border-stone-200";
}

function stagedErrorCount(run: StagedImportRun): number {
  return (
    run.validation_summary?.error_count ??
    run.issues.filter((issue) => issue.severity === "error").length
  );
}

function stagedWarningCount(run: StagedImportRun): number {
  return (
    run.validation_summary?.warning_count ??
    run.issues.filter((issue) => issue.severity === "warning").length
  );
}

function StagedImportPanel({
  busy,
  onBusyChange,
}: {
  busy: boolean;
  onBusyChange: (busy: boolean) => void;
}) {
  const [kind, setKind] = useState<UploadKind>("transactions");
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<StagedImportRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose an Excel file first");
      return api.uploadStagedImport(kind, file);
    },
    onSuccess: (result) => {
      setRun(result);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const applyMutation = useMutation({
    mutationFn: async () => {
      if (!run) throw new Error("Upload a file first");
      return api.applyStagedImport(run.import_run_id);
    },
    onSuccess: (result) => {
      setRun(result);
      setError(null);
      void queryClient.invalidateQueries();
    },
    onError: (err: Error) => setError(err.message),
  });

  const panelBusy = busy || uploadMutation.isPending || applyMutation.isPending;

  useEffect(() => {
    onBusyChange(uploadMutation.isPending || applyMutation.isPending);
  }, [uploadMutation.isPending, applyMutation.isPending, onBusyChange]);

  const errors = run ? stagedErrorCount(run) : 0;
  const warnings = run ? stagedWarningCount(run) : 0;
  const canApply = run != null && run.status === "validated" && errors === 0;
  const applied = run?.status === "applied";

  return (
    <>
      <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
        <h2 className="text-xl font-semibold tracking-tight">Staged import</h2>
        <p className="mt-2 text-sm text-stone-600">
          Upload a Research workbook to private storage, validate it, then apply to the shared
          database. Same file checksum is never imported twice.
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
                    name="staged-kind"
                    value={option.value}
                    checked={kind === option.value}
                    onChange={() => setKind(option.value)}
                    className="mt-1"
                    disabled={panelBusy}
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
                accept=".xlsx,.xlsm,.xls"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="mt-2 block w-full text-sm text-stone-600"
                disabled={panelBusy}
              />
            </label>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                disabled={!file || panelBusy}
                onClick={() => uploadMutation.mutate()}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-stone-300"
              >
                {uploadMutation.isPending ? "Uploading…" : "1. Upload & validate"}
              </button>
              <button
                type="button"
                disabled={!canApply || panelBusy || applied}
                onClick={() => applyMutation.mutate()}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-emerald-200"
              >
                {applyMutation.isPending ? "Applying…" : "2. Apply to database"}
              </button>
            </div>

            {error ? (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
                {error}
              </p>
            ) : null}
          </div>

          <div className="rounded-xl border border-stone-200 bg-stone-50 p-5">
            <h3 className="text-lg font-semibold">Import run</h3>
            {!run ? (
              <p className="mt-3 text-sm text-stone-600">
                No upload yet. Choose a workbook and upload — validation runs automatically.
              </p>
            ) : (
              <div className="mt-4 space-y-3 text-sm">
                <p>
                  <span className="text-stone-500">File</span>{" "}
                  <span className="font-semibold">{run.original_filename}</span>
                </p>
                <p>
                  <span className="text-stone-500">Status</span>{" "}
                  <span className="font-semibold">{run.status}</span>
                  {run.deduplicated ? (
                    <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
                      duplicate checksum
                    </span>
                  ) : null}
                </p>
                <p>
                  <span className="text-stone-500">Issues</span>{" "}
                  <span className="font-semibold">
                    {errors} errors · {warnings} warnings
                  </span>
                </p>
                {run.row_counts && Object.keys(run.row_counts).length > 0 ? (
                  <p className="text-stone-600">
                    Rows:{" "}
                    {Object.entries(run.row_counts)
                      .map(([key, value]) => `${key} ${value}`)
                      .join(" · ")}
                  </p>
                ) : null}
                {run.validation_summary?.episode_summary ? (
                  <p className="text-stone-600">
                    Episodes: {run.validation_summary.episode_summary.episodes} total (
                    {run.validation_summary.episode_summary.open} open /{" "}
                    {run.validation_summary.episode_summary.closed} closed)
                  </p>
                ) : null}
                {run.applied_at ? (
                  <p className="text-emerald-800">
                    Applied {new Date(run.applied_at).toLocaleString()}
                  </p>
                ) : null}
                {errors > 0 ? (
                  <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-900">
                    Apply is blocked until every error is resolved.
                  </p>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </section>

      {run && run.issues.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-2xl font-semibold tracking-tight">Validation results</h2>
          <ul className="space-y-2">
            {run.issues.map((issue, index) => (
              <li
                key={`${issue.code}-${index}`}
                className={`rounded-xl border px-4 py-3 text-sm ${issueSeverityClass(issue.severity)}`}
              >
                <p className="font-semibold">
                  {issue.severity} · {issue.code}
                </p>
                <p className="mt-1">{issue.message}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function LegacyUploadPanel({ busy }: { busy: boolean }) {
  const [kind, setKind] = useState<UploadKind>("transactions");
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<UploadBatch | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const panelBusy =
    busy ||
    uploadMutation.isPending ||
    validateMutation.isPending ||
    commitMutation.isPending;

  return (
    <>
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
                disabled={!file || panelBusy}
                onClick={() => uploadMutation.mutate()}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-stone-300"
              >
                {uploadMutation.isPending ? "Uploading…" : "1. Upload"}
              </button>
              <button
                type="button"
                disabled={!batch || panelBusy}
                onClick={() => validateMutation.mutate()}
                className="rounded-lg border border-stone-300 bg-white px-4 py-2 text-sm font-semibold text-stone-800 disabled:cursor-not-allowed disabled:text-stone-400"
              >
                {validateMutation.isPending ? "Checking…" : "2. Check & calibrate"}
              </button>
              <button
                type="button"
                disabled={!batch?.can_commit || panelBusy || batch.status === "committed"}
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
            <h3 className="text-lg font-semibold">Batch status</h3>
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
                className={`rounded-xl border px-4 py-3 text-sm ${issueSeverityClass(issue.severity)}`}
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
    </>
  );
}

export function DataImportView() {
  const [refreshResult, setRefreshResult] = useState<OnedriveRefreshResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stagedBusy, setStagedBusy] = useState(false);
  const queryClient = useQueryClient();

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    staleTime: 60_000,
  });
  const stagedWorkflow = Boolean(healthQuery.data?.approval_workflow);

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

  const busy = refreshMutation.isPending || stagedBusy;

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
          episode analysis.
          {stagedWorkflow
            ? " Upload new workbooks below via staged import (versioned storage + validation)."
            : " You can also upload a single workbook below for calibration."}
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
                Market data (
                {refreshResult.market_data.used_seed_fallback ? "seed fallback" : "OneDrive path"}
                ): prices +{refreshResult.market_data.prices_inserted} (
                {refreshResult.market_data.prices_skipped} unchanged) · benchmarks +
                {refreshResult.market_data.benchmarks_inserted} · dividends +
                {refreshResult.market_data.dividends_inserted}
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
            {refreshResult.notes?.length ? (
              <p className="mt-1">{refreshResult.notes.join(" · ")}</p>
            ) : null}
          </div>
        ) : null}
      </section>

      {error ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
          {error}
        </p>
      ) : null}

      {stagedWorkflow ? (
        <section className="space-y-4">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">DailyEdit cloud sync</h2>
            <p className="mt-1 text-sm text-stone-600">
              Upload workbooks from your Mac, then preview/apply reimport. Lives only on this
              Admin → Data page — not on Client / Charts strategy screens.
            </p>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {DAILY_EDIT_PANELS.map((panel) => (
              <DailyEditPanel
                key={panel.category}
                category={panel.category}
                title={panel.title}
              />
            ))}
          </div>
        </section>
      ) : null}

      {stagedWorkflow ? (
        <StagedImportPanel busy={busy} onBusyChange={setStagedBusy} />
      ) : (
        <LegacyUploadPanel busy={busy} />
      )}

      <section className="border-t border-stone-200 pt-6 text-sm text-stone-500">
        <h2 className="text-lg font-semibold text-stone-800">Refresh scope</h2>
        <p className="mt-2 max-w-3xl leading-6">
          Refresh handles both portfolio imports and market-data/analysis rebuild. For best
          results on Windows Docker, set both{" "}
          <code className="rounded bg-stone-100 px-1">RESEARCH_DIR</code> and{" "}
          <code className="rounded bg-stone-100 px-1">ONEDRIVE_EXTERNAL_DATA_DIR</code> in
          <code className="rounded bg-stone-100 px-1">.env</code> so the app prefers OneDrive
          data over bundled seed fallbacks.
        </p>
      </section>
    </div>
  );
}
