"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type BhavRun, type PivotDashboard } from "@/lib/api";
import { formatDate } from "@/lib/format";

type TabId = "upload" | "daily";
type DailyScope = "all" | "portfolio" | "selected";
type SeriesScope = "both" | "EQ" | "BE";

const TABS: { id: TabId; label: string }[] = [
  { id: "upload", label: "Upload bhav" },
  { id: "daily", label: "Daily" },
];

const PRESELECT_KEY = "pivot-preselect-symbols";
const SELECTED_FIRMS_KEY = "pivot-selected-firms";

/** YYYY-MM-DD in Asia/Kolkata (matches NSE bhav “today”). */
function todayIstInput(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

function loadSelectedFirms(): string[] {
  try {
    const raw = localStorage.getItem(SELECTED_FIRMS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.map((s) => String(s).toUpperCase()).filter(Boolean);
  } catch {
    return [];
  }
}

function num(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function pivotNum(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

function apiDetail(err: Error): string {
  try {
    const parsed = JSON.parse(err.message) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    /* plain text */
  }
  return err.message;
}

export function PivotPointStrategyView() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabId>("daily");
  const [asOf, setAsOf] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<BhavRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [dailyScope, setDailyScope] = useState<DailyScope>("portfolio");
  const [seriesScope, setSeriesScope] = useState<SeriesScope>("both");
  const [showPrevDayVol, setShowPrevDayVol] = useState(false);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(loadSelectedFirms);
  const selectedHydrated = useRef(false);
  const [newFirm, setNewFirm] = useState("");
  const [addFirmError, setAddFirmError] = useState<string | null>(null);
  const [firmSuggestOpen, setFirmSuggestOpen] = useState(false);
  const [fetchMsg, setFetchMsg] = useState<string | null>(null);
  const [pullDate, setPullDate] = useState(todayIstInput);

  const dashQuery = useQuery({
    queryKey: ["pivot-dashboard", asOf ?? "latest", dailyScope, selectedSymbols.join(",")],
    queryFn: () =>
      api.getPivotDashboard(asOf, {
        scope: dailyScope,
        symbols: dailyScope === "selected" ? selectedSymbols : undefined,
      }),
  });

  const data = dashQuery.data;

  // Julesh-only PCs often have empty episode-based holding_symbols; Client Portfolio Model works.
  const clientBookQuery = useQuery({
    queryKey: ["client-portfolio-dashboard", "client", asOf ?? data?.as_of ?? "latest"],
    queryFn: () =>
      api.getClientPortfolioDashboard(asOf ?? data?.as_of ?? null, "client"),
  });

  const fetchNseMutation = useMutation({
    mutationFn: () => api.fetchNseBhav(pullDate || null),
    onSuccess: (result) => {
      setFetchMsg(result.message);
      setAsOf(result.trade_date);
      if (result.trade_date) setPullDate(result.trade_date);
      void queryClient.invalidateQueries({ queryKey: ["pivot-dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
    },
    onError: (err: Error) => setFetchMsg(apiDetail(err)),
  });

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(PRESELECT_KEY);
      if (!raw) return;
      const symbols = JSON.parse(raw) as string[];
      sessionStorage.removeItem(PRESELECT_KEY);
      if (!Array.isArray(symbols) || !symbols.length) return;
      setSelectedSymbols(symbols.map((s) => String(s).toUpperCase()));
      setDailyScope("selected");
      setTab("daily");
    } catch {
      /* ignore */
    }
  }, []);

  const holdingSymbols = useMemo(() => {
    const names = new Set<string>();
    for (const symbol of data?.holding_symbols ?? []) {
      if (symbol) names.add(symbol);
    }
    for (const row of clientBookQuery.data?.holdings ?? []) {
      if (row.symbol) names.add(row.symbol);
    }
    for (const symbol of clientBookQuery.data?.model_symbols ?? []) {
      if (symbol) names.add(symbol);
    }
    names.delete("LIQUIDCASE");
    return [...names].sort();
  }, [
    data?.holding_symbols,
    clientBookQuery.data?.holdings,
    clientBookQuery.data?.model_symbols,
  ]);
  const holdingSet = useMemo(() => new Set(holdingSymbols), [holdingSymbols]);
  // DB order = selection order (no alpha sort).
  const pivotWatchSymbols = useMemo(
    () => (data?.portfolio ?? []).map((p) => p.symbol),
    [data?.portfolio],
  );
  const selectedSet = useMemo(() => new Set(selectedSymbols), [selectedSymbols]);

  useEffect(() => {
    try {
      localStorage.setItem(SELECTED_FIRMS_KEY, JSON.stringify(selectedSymbols));
    } catch {
      /* ignore */
    }
  }, [selectedSymbols]);

  // After refresh: keep checked firms still in the watchlist; if none, check all.
  useEffect(() => {
    if (!pivotWatchSymbols.length) return;
    const watch = new Set(pivotWatchSymbols);
    setSelectedSymbols((prev) => {
      const kept = prev.filter((s) => watch.has(s));
      if (!selectedHydrated.current) {
        selectedHydrated.current = true;
        return kept.length ? kept : [...pivotWatchSymbols];
      }
      return kept;
    });
  }, [pivotWatchSymbols]);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a bhav CSV/XLSX first");
      return api.uploadBhav(file);
    },
    onSuccess: (result) => {
      setRun(result);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      if (!run) throw new Error("Upload first");
      return api.validateBhav(run.run_id);
    },
    onSuccess: (result) => {
      setRun(result);
      setError(result.status === "failed" ? result.error_message : null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (!run) throw new Error("Upload and validate first");
      return api.commitBhav(run.run_id);
    },
    onSuccess: (result) => {
      setRun(result);
      setError(result.status === "failed" ? result.error_message : null);
      if (result.status === "committed" && result.trade_date) {
        setAsOf(result.trade_date);
        void queryClient.invalidateQueries({ queryKey: ["pivot-dashboard"] });
        void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
        void queryClient.invalidateQueries({ queryKey: ["open-holdings"] });
        setTab("daily");
      }
    },
    onError: (err: Error) => setError(err.message),
  });

  const q = query.trim().toLowerCase();
  // Checked firms first (selection order), then unchecked watchlist names.
  const firmListSymbols = useMemo(() => {
    const watch = new Set(pivotWatchSymbols);
    const selected = selectedSymbols.filter((s) => watch.has(s));
    const rest = pivotWatchSymbols.filter((s) => !selectedSet.has(s));
    return [...selected, ...rest];
  }, [pivotWatchSymbols, selectedSymbols, selectedSet]);

  const daily = useMemo(() => {
    let rows = data?.daily ?? [];
    if (seriesScope === "EQ" || seriesScope === "BE") {
      rows = rows.filter((r) => r.series === seriesScope);
    }
    if (dailyScope === "portfolio") {
      rows = rows.filter((r) => holdingSet.has(r.symbol));
    } else if (dailyScope === "selected") {
      rows = rows.filter((r) => selectedSet.has(r.symbol));
      // Order = checkbox / add order (1st selected stays on top) — not A→Z.
      const rank = new Map(selectedSymbols.map((s, i) => [s, i]));
      rows = [...rows].sort(
        (a, b) => (rank.get(a.symbol) ?? 1e9) - (rank.get(b.symbol) ?? 1e9),
      );
    }
    return q ? rows.filter((r) => r.symbol.toLowerCase().includes(q)) : rows;
  }, [
    data?.daily,
    dailyScope,
    seriesScope,
    holdingSet,
    selectedSet,
    selectedSymbols,
    q,
  ]);

  const toggleSelected = (symbol: string) => {
    setSelectedSymbols((prev) =>
      prev.includes(symbol) ? prev.filter((s) => s !== symbol) : [...prev, symbol],
    );
  };

  const selectAllFirms = () => {
    // Keep current selection order; append any missing watchlist names at the end.
    setSelectedSymbols((prev) => {
      const watch = new Set(pivotWatchSymbols);
      const kept = prev.filter((s) => watch.has(s));
      const seen = new Set(kept);
      return [...kept, ...pivotWatchSymbols.filter((s) => !seen.has(s))];
    });
  };

  const firmSearchQuery = newFirm.trim().toUpperCase();
  const firmSuggestQuery = useQuery({
    queryKey: ["pivot-symbol-search", firmSearchQuery],
    queryFn: () => api.searchPivotSymbols(firmSearchQuery),
    enabled: dailyScope === "selected" && firmSearchQuery.length >= 2,
    staleTime: 60_000,
  });
  const firmSuggestions = firmSuggestQuery.data?.symbols ?? [];

  const pickFirm = (symbol: string) => {
    setNewFirm(symbol);
    setFirmSuggestOpen(false);
    setAddFirmError(null);
    void addFirmMutation.mutate(symbol);
  };

  const addFirmMutation = useMutation({
    mutationFn: async (explicit?: string) => {
      const symbol = (explicit ?? newFirm).trim().toUpperCase();
      if (!symbol) throw new Error("Enter a symbol");
      await api.addPivotFirm(symbol);
      return symbol;
    },
    onSuccess: (symbol) => {
      setNewFirm("");
      setFirmSuggestOpen(false);
      setAddFirmError(null);
      setSelectedSymbols((prev) => (prev.includes(symbol) ? prev : [...prev, symbol]));
      void queryClient.invalidateQueries({ queryKey: ["pivot-dashboard"] });
    },
    onError: (err: Error) => setAddFirmError(apiDetail(err)),
  });

  const removeFirmMutation = useMutation({
    mutationFn: (symbol: string) => api.removePivotFirm(symbol),
    onSuccess: (result) => {
      setAddFirmError(null);
      setSelectedSymbols((prev) => prev.filter((s) => s !== result.deleted));
      void queryClient.invalidateQueries({ queryKey: ["pivot-dashboard"] });
    },
    onError: (err: Error) => setAddFirmError(apiDetail(err)),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            Strategy
          </p>
          <h2 className="text-2xl font-semibold text-stone-900">Pivot Point Strategy</h2>
          <p className="mt-1 max-w-2xl text-sm text-stone-600">
            Upload each day&apos;s NSE CM UDiFF bhav copy. Validate → commit, then review
            the Daily sheet (pivots, Vol Exp, 15min bands).
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-stone-600">
            As-of date
            <select
              className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-stone-900 shadow-sm"
              value={asOf ?? data?.as_of ?? ""}
              onChange={(e) => setAsOf(e.target.value || null)}
            >
              {(data?.available_dates?.length ? data.available_dates : []).map((d) => (
                <option key={d} value={d}>
                  {formatDate(d)}
                </option>
              ))}
              {!data?.available_dates?.length ? <option value="">No bhav days yet</option> : null}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-stone-600">
            Pull date
            <input
              type="date"
              className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-stone-900 shadow-sm"
              value={pullDate}
              max={todayIstInput()}
              onChange={(e) => setPullDate(e.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={fetchNseMutation.isPending || !pullDate}
            onClick={() => {
              setFetchMsg(null);
              fetchNseMutation.mutate();
            }}
            className="rounded-lg border border-emerald-700 bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {fetchNseMutation.isPending ? "Pulling NSE…" : "Pull bhav"}
          </button>
          {asOf && data?.available_dates?.[0] && asOf !== data.available_dates[0] ? (
            <button
              type="button"
              onClick={() => setAsOf(null)}
              className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900 hover:bg-amber-100"
            >
              Jump to latest ({formatDate(data.available_dates[0])})
            </button>
          ) : null}
        </div>
      </div>
      {data?.as_of ? (
        <p className="text-sm text-stone-500">
          Showing bhav for <span className="font-medium text-stone-800">{formatDate(data.as_of)}</span>
          {data.available_dates?.[0] && data.as_of !== data.available_dates[0]
            ? ` (latest committed is ${formatDate(data.available_dates[0])})`
            : null}
        </p>
      ) : null}
      {fetchMsg ? (
        <p
          className={`rounded-lg border px-3 py-2 text-sm ${
            fetchNseMutation.isError
              ? "border-red-200 bg-red-50 text-red-800"
              : "border-stone-200 bg-stone-50 text-stone-700"
          }`}
        >
          {fetchMsg}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              tab === item.id
                ? "bg-emerald-700 text-white"
                : "bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-50"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "daily" ? (
        <>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by symbol…"
            className="w-full max-w-xs rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm shadow-sm outline-none ring-emerald-600/30 focus:ring-2"
          />
          <div className="space-y-3 rounded-xl border border-stone-200 bg-white p-4">
            <div className="flex flex-wrap items-center gap-4 text-sm text-stone-700">
              <span className="font-medium text-stone-500">Show</span>
              {(
                [
                  ["all", "All"],
                  ["portfolio", "Our holdings"],
                  ["selected", "Selected firms"],
                ] as const
              ).map(([value, label]) => (
                <label key={value} className="flex cursor-pointer items-center gap-2">
                  <input
                    type="radio"
                    name="daily-scope"
                    checked={dailyScope === value}
                    onChange={() => setDailyScope(value)}
                    className="text-emerald-700 focus:ring-emerald-600"
                  />
                  {label}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-stone-700">
              <span className="font-medium text-stone-500">Series</span>
              {(
                [
                  ["both", "EQ + BE"],
                  ["EQ", "EQ only"],
                  ["BE", "BE only"],
                ] as const
              ).map(([value, label]) => (
                <label key={value} className="flex cursor-pointer items-center gap-2">
                  <input
                    type="radio"
                    name="series-scope"
                    checked={seriesScope === value}
                    onChange={() => setSeriesScope(value)}
                    className="text-emerald-700 focus:ring-emerald-600"
                  />
                  {label}
                </label>
              ))}
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-stone-700">
              <input
                type="checkbox"
                checked={showPrevDayVol}
                onChange={(e) => setShowPrevDayVol(e.target.checked)}
                className="rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
              />
              Prev day vol
            </label>
            {showPrevDayVol ? (
              <span className="text-xs text-stone-500">
                Yesterday&apos;s traded volume (prior bhav TtlTradgVol); 15min bands use vol ÷ 25.
              </span>
            ) : null}
            {dailyScope === "selected" ? (
              <div className="space-y-2">
                <div className="flex flex-wrap items-end gap-2">
                  <div className="relative flex flex-col gap-1 text-xs text-stone-600">
                    <span>Add firm (NSE symbol)</span>
                    <input
                      type="text"
                      value={newFirm}
                      onChange={(e) => {
                        setNewFirm(e.target.value.toUpperCase());
                        setFirmSuggestOpen(true);
                        setAddFirmError(null);
                      }}
                      onFocus={() => setFirmSuggestOpen(true)}
                      onBlur={() => {
                        window.setTimeout(() => setFirmSuggestOpen(false), 150);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          if (firmSuggestions[0]) {
                            pickFirm(firmSuggestions[0]);
                          } else {
                            void addFirmMutation.mutate(undefined);
                          }
                        } else if (e.key === "Escape") {
                          setFirmSuggestOpen(false);
                        }
                      }}
                      placeholder="Type 2+ letters…"
                      autoComplete="off"
                      className="w-44 rounded border border-stone-200 bg-white px-2 py-1.5 text-sm text-stone-900 shadow-sm outline-none ring-emerald-600/30 focus:ring-2"
                    />
                    {firmSuggestOpen && firmSearchQuery.length >= 2 ? (
                      <ul className="absolute left-0 top-full z-20 mt-1 max-h-48 w-44 overflow-y-auto rounded-lg border border-stone-200 bg-white py-1 text-sm shadow-lg">
                        {firmSuggestQuery.isFetching ? (
                          <li className="px-3 py-1.5 text-stone-400">Searching…</li>
                        ) : null}
                        {!firmSuggestQuery.isFetching && !firmSuggestions.length ? (
                          <li className="px-3 py-1.5 text-stone-400">No matches</li>
                        ) : null}
                        {firmSuggestions.map((symbol) => (
                          <li key={symbol}>
                            <button
                              type="button"
                              className="block w-full px-3 py-1.5 text-left text-stone-800 hover:bg-emerald-50"
                              onMouseDown={(e) => e.preventDefault()}
                              onClick={() => pickFirm(symbol)}
                            >
                              {symbol}
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    disabled={!newFirm.trim() || addFirmMutation.isPending}
                    onClick={() => void addFirmMutation.mutate(undefined)}
                    className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
                  >
                    {addFirmMutation.isPending ? "Adding…" : "Add"}
                  </button>
                  <button
                    type="button"
                    className="rounded border border-stone-200 px-2 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
                    onClick={selectAllFirms}
                  >
                    Select all ({pivotWatchSymbols.length})
                  </button>
                  <button
                    type="button"
                    className="rounded border border-stone-200 px-2 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
                    onClick={() => setSelectedSymbols([])}
                  >
                    Clear
                  </button>
                  <span className="self-center text-xs text-stone-500">
                    {selectedSymbols.length} selected · order = check/add order
                  </span>
                </div>
                {addFirmError ? (
                  <p className="text-xs text-red-700">{addFirmError}</p>
                ) : null}
                <div className="max-h-40 overflow-y-auto rounded-lg border border-stone-100 bg-stone-50 p-2">
                  <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 md:grid-cols-4">
                    {firmListSymbols.map((symbol) => (
                      <div
                        key={symbol}
                        className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-stone-700 hover:bg-white"
                      >
                        <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            checked={selectedSet.has(symbol)}
                            onChange={() => toggleSelected(symbol)}
                            className="rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
                          />
                          <span className="truncate">{symbol}</span>
                        </label>
                        <button
                          type="button"
                          title={`Remove ${symbol} from selected firms`}
                          disabled={removeFirmMutation.isPending}
                          onClick={() => void removeFirmMutation.mutate(symbol)}
                          className="shrink-0 rounded px-1 text-stone-400 hover:bg-red-50 hover:text-red-700 disabled:opacity-40"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                  {!pivotWatchSymbols.length ? (
                    <p className="p-2 text-xs text-stone-500">
                      No firms yet — add a symbol above, or run seed-pivot-from-research.
                    </p>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
          {dailyScope === "portfolio" && daily.length === 0 ? (
            <p className="text-sm text-amber-800">
              {holdingSymbols.length === 0
                ? "Our holdings is empty — no symbols from Client Portfolio yet. Click All to see the full market, or confirm PMS_ClientPortfolio*.xlsx is in DailyEditFiles."
                : `Our holdings has ${holdingSymbols.length} symbol${holdingSymbols.length === 1 ? "" : "s"}, but none are in today's bhav (${data?.as_of ?? "—"}). Click All to verify bhav, or pull/upload that day's Final.`}
            </p>
          ) : null}
        </>
      ) : null}

      {tab === "upload" ? (
        <UploadPanel
          file={file}
          setFile={setFile}
          run={run}
          error={error}
          busy={
            uploadMutation.isPending ||
            validateMutation.isPending ||
            commitMutation.isPending
          }
          onUpload={() => void uploadMutation.mutate()}
          onValidate={() => void validateMutation.mutate()}
          onCommit={() => void commitMutation.mutate()}
          lastRun={data?.last_run ?? null}
        />
      ) : null}

      {dashQuery.isLoading && tab === "daily" ? (
        <p className="text-stone-600">Loading dashboard…</p>
      ) : null}
      {dashQuery.isError && tab === "daily" ? (
        <p className="text-red-700">{(dashQuery.error as Error).message}</p>
      ) : null}

      {tab === "daily" && data ? (
        <DailySheetTable
          title={`Daily (${daily.length})`}
          rows={daily}
          showPrevDayVol={showPrevDayVol}
        />
      ) : null}
    </div>
  );
}

function UploadPanel({
  file,
  setFile,
  run,
  error,
  busy,
  onUpload,
  onValidate,
  onCommit,
  lastRun,
}: {
  file: File | null;
  setFile: (f: File | null) => void;
  run: BhavRun | null;
  error: string | null;
  busy: boolean;
  onUpload: () => void;
  onValidate: () => void;
  onCommit: () => void;
  lastRun: PivotDashboard["last_run"];
}) {
  return (
    <div className="space-y-4 rounded-xl border border-stone-200 bg-white p-6">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-stone-600">
          NSE CM UDiFF bhav (CSV / XLSX)
          <input
            type="file"
            accept=".csv,.xlsx,.xls,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm"
          />
        </label>
        <button
          type="button"
          disabled={!file || busy}
          onClick={onUpload}
          className="rounded-lg bg-stone-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          1. Upload
        </button>
        <button
          type="button"
          disabled={!run || busy}
          onClick={onValidate}
          className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-medium disabled:opacity-40"
        >
          2. Validate
        </button>
        <button
          type="button"
          disabled={!run || busy || run.status === "failed"}
          onClick={onCommit}
          className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          3. Commit
        </button>
      </div>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {run ? (
        <div className="rounded-lg border border-stone-200 bg-stone-50 p-4 text-sm text-stone-700">
          <p>
            Run #{run.run_id} · <span className="font-semibold">{run.status}</span> ·{" "}
            {run.source_filename}
            {run.trade_date ? ` · ${formatDate(run.trade_date)}` : ""} · rows{" "}
            {run.row_count_all} (EQ {run.row_count_eq})
          </p>
          {run.validation_report?.errors?.length ? (
            <ul className="mt-2 list-disc pl-5 text-red-700">
              {run.validation_report.errors.slice(0, 8).map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          ) : null}
          {run.reconcile_report?.errors?.length ? (
            <ul className="mt-2 list-disc pl-5 text-red-700">
              {run.reconcile_report.errors.slice(0, 8).map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          ) : null}
          {run.reconcile_report?.ok ? (
            <p className="mt-2 text-emerald-800">Reconcile passed.</p>
          ) : null}
        </div>
      ) : null}
      {lastRun ? (
        <p className="text-xs text-stone-500">
          Last committed: {lastRun.source_filename}
          {lastRun.trade_date ? ` · ${formatDate(lastRun.trade_date)}` : ""} · EQ{" "}
          {lastRun.row_count_eq}
        </p>
      ) : null}
    </div>
  );
}

function DailySheetTable({
  title,
  rows,
  showPrevDayVol,
}: {
  title: string;
  rows: PivotDashboard["daily"];
  showPrevDayVol: boolean;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-stone-700">{title}</h3>
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.06em] text-stone-500">
            <tr>
              <th className="px-3 py-2">TradDt</th>
              <th className="px-3 py-2">TckrSymb</th>
              <th className="px-3 py-2">SctySrs</th>
              <th className="px-3 py-2 text-right bg-red-50">S4-0.3</th>
              <th className="px-3 py-2 text-right">S3-0.3</th>
              <th className="px-3 py-2 text-right">S2-03</th>
              <th className="px-3 py-2 text-right">S1-03</th>
              <th className="px-3 py-2 text-right">Pivot</th>
              <th className="px-3 py-2 text-right">R1+0.3</th>
              <th className="px-3 py-2 text-right">R2+0.3</th>
              <th className="px-3 py-2 text-right">R3+0.3</th>
              <th className="px-3 py-2 text-right bg-blue-50">R4+0.3</th>
              <th className="px-3 py-2 text-right">
                {showPrevDayVol ? "Prev vol" : "Vol Exp"}
              </th>
              <th className="px-3 py-2 text-right">15minVol</th>
              <th className="px-3 py-2 text-right">Top50</th>
              <th className="px-3 py-2 text-right">51=300</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 500).map((row) => {
              const p = row.pivot;
              const miss = !p || p.missing;
              const volValue = showPrevDayVol ? row.prev_day_volume : row.vol_exp;
              const vol15 = volValue != null ? volValue / 25 : null;
              const top50 = vol15 != null ? vol15 * 3 : null;
              const band51300 = vol15 != null ? vol15 * 6 : null;
              return (
                <tr
                  key={`${row.trade_date}-${row.symbol}-${row.series}`}
                  className="border-t border-stone-100"
                >
                  <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(row.trade_date)}</td>
                  <td className="px-3 py-1.5 font-medium">{row.symbol}</td>
                  <td className="px-3 py-1.5">{row.series}</td>
                  <td className="bg-red-50 px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.s4_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.s3_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.s2_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.s1_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.pp)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.r1_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.r2_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.r3_03)}
                  </td>
                  <td className="bg-blue-50 px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.r4_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {num(volValue, 0)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(vol15, 0)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(top50, 0)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(band51300)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {rows.length > 500 ? (
        <p className="text-xs text-stone-500">Showing first 500 of {rows.length}. Filter to narrow.</p>
      ) : null}
    </div>
  );
}
