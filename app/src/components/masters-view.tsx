"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type MasterApplyResult,
  type MasterKind,
  type ProposedMasterEdit,
} from "@/lib/api";

const TABS: { kind: MasterKind; label: string }[] = [
  { kind: "security", label: "Security Master" },
  { kind: "transactions", label: "Transactions" },
  { kind: "sell_since", label: "Sell Since" },
];

const PROMPT_HELP = `Examples:
BUY Havells 100 @ 1501.25 on 2026-07-15 note=top-up
SELL RELIANCE 50 @ 1300 on 2026-07-20
UPDATE SECURITY HAVELLS sector=Consumer industry=Electrical
SELL_SINCE stock=ExampleCo sell_date=2026-01-15 sell_price=120 note=manual`;

export function MastersView() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<MasterKind>("transactions");
  const [sheet, setSheet] = useState<string | undefined>(undefined);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [prompt, setPrompt] = useState("");
  const [edits, setEdits] = useState<ProposedMasterEdit[] | null>(null);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [applyResult, setApplyResult] = useState<MasterApplyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const limit = 40;

  const mastersQuery = useQuery({
    queryKey: ["masters"],
    queryFn: () => api.listMasters(),
  });

  const previewQuery = useQuery({
    queryKey: ["masters-preview", kind, sheet, offset, search],
    queryFn: () =>
      api.getMasterPreview(kind, {
        sheet,
        offset,
        limit,
        q: search || undefined,
      }),
  });

  const activeMeta = useMemo(
    () => mastersQuery.data?.find((row) => row.kind === kind),
    [mastersQuery.data, kind],
  );

  const parseMutation = useMutation({
    mutationFn: () => api.parseMasterPrompt(prompt, kind),
    onSuccess: (result) => {
      setEdits(result.edits);
      setParseErrors(result.errors);
      setApplyResult(null);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const applyMutation = useMutation({
    mutationFn: async () => {
      if (!edits?.length) throw new Error("Parse a prompt first");
      if (parseErrors.length) throw new Error("Fix parse errors before applying");
      return api.applyMasterEdits(edits, true);
    },
    onSuccess: (result) => {
      setApplyResult(result);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["masters"] });
      void queryClient.invalidateQueries({ queryKey: ["masters-preview"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const preview = previewQuery.data;
  const columns = preview?.columns ?? [];
  const rows = preview?.rows ?? [];
  const busy = parseMutation.isPending || applyMutation.isPending;

  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
          Final masters
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-stone-900">
          Excel source of truth
        </h2>
        <p className="mt-2 text-sm text-stone-600">
          Browse Security Master, Transactions, and Sell Since. Enter trade or field
          updates as prompt lines, review the proposed edits, then apply — writes the
          Final Master workbook, syncs into{" "}
          <code className="rounded bg-stone-100 px-1">data/raw</code>, and reimports
          security/transactions into the database.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.kind}
            type="button"
            onClick={() => {
              setKind(tab.kind);
              setSheet(undefined);
              setOffset(0);
              setEdits(null);
              setParseErrors([]);
              setApplyResult(null);
            }}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
              kind === tab.kind
                ? "bg-emerald-700 text-white"
                : "bg-white text-stone-700 ring-1 ring-stone-200 hover:bg-stone-50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeMeta ? (
        <section className="rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
          <p>
            <span className="font-medium text-stone-900">{activeMeta.label}</span>
            {activeMeta.exists ? (
              <>
                {" · "}
                updated {activeMeta.mtime ?? "—"}
                {activeMeta.size_bytes != null
                  ? ` · ${(activeMeta.size_bytes / 1024).toFixed(0)} KB`
                  : ""}
              </>
            ) : (
              <span className="text-red-700"> · file missing</span>
            )}
          </p>
          <p className="mt-1 truncate font-mono text-xs text-stone-500">{activeMeta.path}</p>
          <div className="mt-3">
            <a
              href={api.masterDownloadUrl(kind)}
              className="inline-flex rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-stone-800"
            >
              Download workbook
            </a>
          </div>
        </section>
      ) : null}

      <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-stone-500">
              Sheet
            </span>
            <select
              className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
              value={sheet ?? preview?.sheet ?? ""}
              onChange={(e) => {
                setSheet(e.target.value || undefined);
                setOffset(0);
              }}
            >
              {(preview?.sheets ?? [activeMeta?.default_sheet ?? "Sheet1"]).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-[16rem] flex-1 text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-stone-500">
              Filter
            </span>
            <div className="flex gap-2">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setSearch(q);
                    setOffset(0);
                  }
                }}
                placeholder="Search stock / symbol / text"
                className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
              />
              <button
                type="button"
                className="rounded-lg bg-stone-100 px-3 py-2 text-sm font-medium hover:bg-stone-200"
                onClick={() => {
                  setSearch(q);
                  setOffset(0);
                }}
              >
                Search
              </button>
            </div>
          </label>
        </div>

        {previewQuery.isLoading ? (
          <p className="text-sm text-stone-500">Loading preview…</p>
        ) : previewQuery.isError ? (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {(previewQuery.error as Error).message}
          </p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-stone-200">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-stone-50 text-stone-600">
                  <tr>
                    <th className="px-2 py-2 font-medium">#</th>
                    {columns.slice(0, 10).map((col) => (
                      <th key={col} className="whitespace-nowrap px-2 py-2 font-medium">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={String(row._row)} className="border-t border-stone-100">
                      <td className="px-2 py-1.5 text-stone-400">{row._row}</td>
                      {columns.slice(0, 10).map((col) => (
                        <td key={col} className="max-w-[12rem] truncate px-2 py-1.5">
                          {row[col] == null ? "" : String(row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {rows.length === 0 ? (
                    <tr>
                      <td
                        colSpan={Math.min(columns.length, 10) + 1}
                        className="px-3 py-6 text-center text-stone-500"
                      >
                        No rows
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-stone-500">
              <span>
                Showing {rows.length} of {preview?.matched_rows ?? 0} matched
                {preview ? ` (${preview.total_rows} total)` : ""}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset <= 0}
                  className="rounded border border-stone-200 px-2 py-1 disabled:opacity-40"
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                >
                  Prev
                </button>
                <button
                  type="button"
                  disabled={!preview || offset + limit >= preview.matched_rows}
                  className="rounded border border-stone-200 px-2 py-1 disabled:opacity-40"
                  onClick={() => setOffset(offset + limit)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-stone-900">Prompt updates</h3>
        <p className="mt-1 whitespace-pre-wrap text-xs text-stone-500">{PROMPT_HELP}</p>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={6}
          className="mt-3 w-full rounded-lg border border-stone-300 px-3 py-2 font-mono text-sm"
          placeholder="One edit per line…"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy || !prompt.trim()}
            onClick={() => parseMutation.mutate()}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
          >
            {parseMutation.isPending ? "Parsing…" : "Parse"}
          </button>
          <button
            type="button"
            disabled={
              busy || !edits?.length || parseErrors.length > 0 || applyMutation.isPending
            }
            onClick={() => applyMutation.mutate()}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            {applyMutation.isPending ? "Applying…" : "Apply to Excel & reimport"}
          </button>
        </div>

        {parseErrors.length > 0 ? (
          <ul className="mt-3 space-y-1 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {parseErrors.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}

        {edits && edits.length > 0 ? (
          <ul className="mt-3 divide-y divide-stone-100 rounded-lg border border-stone-200">
            {edits.map((edit) => (
              <li key={`${edit.line_number}-${edit.summary}`} className="px-3 py-2 text-sm">
                <p className="font-medium text-stone-900">{edit.summary}</p>
                <p className="font-mono text-xs text-stone-500">{edit.raw_line}</p>
                {edit.warnings?.length ? (
                  <p className="text-xs text-amber-800">{edit.warnings.join("; ")}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}

        {error ? (
          <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {error}
          </p>
        ) : null}

        {applyResult ? (
          <div className="mt-3 space-y-1 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-950">
            <p>
              Applied {applyResult.applied} edit(s)
              {applyResult.episode_count != null
                ? ` · episodes=${applyResult.episode_count}`
                : ""}
            </p>
            {applyResult.import_notes.map((note) => (
              <p key={note}>{note}</p>
            ))}
            {applyResult.backups[0] ? (
              <p className="font-mono text-xs">Backup: {applyResult.backups[0]}</p>
            ) : null}
            {applyResult.errors.map((item) => (
              <p key={item} className="text-red-800">
                {item}
              </p>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
