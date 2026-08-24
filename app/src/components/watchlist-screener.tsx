"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  api,
  type MetricDefinition,
  type WatchlistScreenRow,
} from "@/lib/api";
import { formatPct, formatPp, toneClass, valueTone } from "@/lib/format";

const STORAGE_KEY = "watchlist-screener-view-v1";

type SavedView = {
  columns: string[];
  sort: string | null;
};

const DEFAULT_COLUMNS = ["sales", "sales_yoy_pct", "opm", "pat_yoy_pct"];

function loadSavedView(): SavedView {
  if (typeof window === "undefined") {
    return { columns: DEFAULT_COLUMNS, sort: "sales_yoy_pct:desc" };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { columns: DEFAULT_COLUMNS, sort: "sales_yoy_pct:desc" };
    }
    const parsed = JSON.parse(raw) as SavedView;
    return {
      columns: parsed.columns?.length ? parsed.columns : DEFAULT_COLUMNS,
      sort: parsed.sort ?? "sales_yoy_pct:desc",
    };
  } catch {
    return { columns: DEFAULT_COLUMNS, sort: "sales_yoy_pct:desc" };
  }
}

function persistView(view: SavedView) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(view));
}

function formatMetric(value: number | null | undefined, format: string): string {
  if (value === null || value === undefined) return "—";
  if (format === "currency_cr") {
    return new Intl.NumberFormat("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }
  if (format === "percent" || format === "percent_signed") {
    return formatPct(value, 2, { signed: format === "percent_signed" });
  }
  if (format === "pp_signed") {
    return formatPp(value);
  }
  if (format === "number") {
    return new Intl.NumberFormat("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }
  return String(value);
}

function quarterLabel(row: WatchlistScreenRow): string {
  if (!row.fiscal_year || !row.fiscal_quarter) return "—";
  return `${row.fiscal_quarter}FY${String(row.fiscal_year).slice(-2)}`;
}

export function WatchlistScreener({ watchlistId }: { watchlistId: number }) {
  const [savedView, setSavedView] = useState<SavedView>(() => loadSavedView());
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draftColumns, setDraftColumns] = useState<string[]>(savedView.columns);

  useEffect(() => {
    setSavedView(loadSavedView());
  }, []);

  useEffect(() => {
    persistView(savedView);
  }, [savedView]);

  const catalogQuery = useQuery({
    queryKey: ["watchlist-metric-catalog"],
    queryFn: () => api.listWatchlistMetricCatalog(),
  });

  const screenQuery = useQuery({
    queryKey: ["watchlist-screen", watchlistId, savedView.columns, savedView.sort],
    queryFn: () =>
      api.getWatchlistScreen(watchlistId, {
        columns: savedView.columns.join(","),
        sort: savedView.sort ?? undefined,
      }),
    enabled: watchlistId > 0,
  });

  const catalog = catalogQuery.data ?? [];
  const catalogByKey = useMemo(
    () => Object.fromEntries(catalog.map((m) => [m.key, m])),
    [catalog],
  );

  const groupedMetrics = useMemo(() => {
    const groups = new Map<string, MetricDefinition[]>();
    for (const metric of catalog) {
      const list = groups.get(metric.group) ?? [];
      list.push(metric);
      groups.set(metric.group, list);
    }
    return [...groups.entries()];
  }, [catalog]);

  const rows = screenQuery.data?.rows ?? [];
  const staleCount = rows.filter((row) => row.fundamentals_stale).length;
  const missingCount = rows.filter((row) => !row.has_fundamentals).length;

  const toggleSort = (column: string) => {
    const current = savedView.sort;
    const [currentCol, currentDir] = current?.includes(":")
      ? (current.split(":") as [string, string])
      : [current, "asc"];
    if (currentCol === column) {
      const nextDir = currentDir === "asc" ? "desc" : "asc";
      setSavedView((prev) => ({ ...prev, sort: `${column}:${nextDir}` }));
      return;
    }
    setSavedView((prev) => ({ ...prev, sort: `${column}:desc` }));
  };

  const sortIndicator = (column: string) => {
    const sort = savedView.sort;
    if (!sort?.startsWith(`${column}:`)) return "";
    return sort.endsWith(":desc") ? " ↓" : " ↑";
  };

  const applyColumns = () => {
    setSavedView((prev) => ({ ...prev, columns: draftColumns }));
    setPickerOpen(false);
  };

  const exportCsv = async () => {
    const blob = await api.exportWatchlistScreenCsv(watchlistId, {
      columns: savedView.columns.join(","),
      sort: savedView.sort ?? undefined,
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `watchlist_${watchlistId}_screen.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (catalogQuery.isLoading || screenQuery.isLoading) {
    return <p className="text-stone-600">Loading screener…</p>;
  }

  if (screenQuery.isError) {
    return <p className="text-red-700">Could not load screener data.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-stone-600">
          {rows.length} stocks · sorted by{" "}
          <span className="font-medium text-stone-800">
            {savedView.sort?.replace(":", " ") ?? "default"}
          </span>
        </p>
        {staleCount > 0 ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
            {staleCount} stale (&gt;90d)
          </span>
        ) : null}
        {missingCount > 0 ? (
          <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-700">
            {missingCount} no fundamentals — run Refresh all or wait for weekly job
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => {
            setDraftColumns(savedView.columns);
            setPickerOpen((open) => !open);
          }}
          className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50"
        >
          Columns
        </button>
        <button
          type="button"
          onClick={() => exportCsv()}
          className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50"
        >
          Export CSV
        </button>
      </div>
      <p className="text-xs text-stone-500">
        Screener reads saved data from the database. Use Refresh all or the weekly scheduled job to update metrics.
      </p>

      {pickerOpen ? (
        <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-stone-500">
            Visible columns
          </p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {groupedMetrics.map(([group, metrics]) => (
              <div key={group}>
                <p className="text-xs font-medium text-stone-700">{group}</p>
                <ul className="mt-2 space-y-1">
                  {metrics.map((metric) => (
                    <li key={metric.key}>
                      <label className="flex items-center gap-2 text-sm text-stone-700">
                        <input
                          type="checkbox"
                          checked={draftColumns.includes(metric.key)}
                          onChange={(e) => {
                            setDraftColumns((cols) =>
                              e.target.checked
                                ? [...cols, metric.key]
                                : cols.filter((c) => c !== metric.key),
                            );
                          }}
                        />
                        {metric.label}
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={applyColumns}
              className="rounded-lg bg-emerald-800 px-3 py-1.5 text-xs font-medium text-white"
            >
              Apply
            </button>
            <button
              type="button"
              onClick={() => setPickerOpen(false)}
              className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs text-stone-600"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
        <table className="min-w-full text-sm">
          <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.08em] text-stone-500">
            <tr>
              <th className="px-4 py-3">
                <button type="button" onClick={() => toggleSort("display_name")} className="hover:text-stone-800">
                  Company{sortIndicator("display_name")}
                </button>
              </th>
              <th className="px-4 py-3">NSE</th>
              <th className="px-4 py-3">Quarter</th>
              <th className="px-4 py-3">Data</th>
              {savedView.columns.map((key) => (
                <th key={key} className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => toggleSort(key)}
                    className="hover:text-stone-800"
                  >
                    {catalogByKey[key]?.label ?? key}
                    {sortIndicator(key)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={4 + savedView.columns.length}
                  className="px-4 py-8 text-center text-stone-500"
                >
                  No watchlist members to screen.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.member_id}
                  className={`border-t border-stone-100 hover:bg-stone-50/80 ${
                    row.fundamentals_stale ? "bg-amber-50/40" : ""
                  }`}
                >
                  <td className="px-4 py-3">
                    <p className="font-medium">{row.display_name}</p>
                    <p className="text-xs text-stone-500">{row.sector ?? row.industry ?? ""}</p>
                  </td>
                  <td className="px-4 py-3 tabular-nums text-stone-600">{row.nse_symbol ?? "—"}</td>
                  <td className="px-4 py-3 text-stone-600">{quarterLabel(row)}</td>
                  <td className="px-4 py-3">
                    {!row.has_fundamentals ? (
                      <span className="text-xs text-stone-400">No data</span>
                    ) : row.fundamentals_stale ? (
                      <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-amber-900">
                        Stale
                      </span>
                    ) : (
                      <span className="text-xs text-emerald-700">OK</span>
                    )}
                  </td>
                  {savedView.columns.map((key) => {
                    const metric = catalogByKey[key];
                    const value = row.metrics[key];
                    const tone =
                      metric?.format === "percent_signed" || metric?.format === "pp_signed"
                        ? valueTone(value)
                        : "neutral";
                    return (
                      <td
                        key={key}
                        className={`px-4 py-3 text-right tabular-nums ${toneClass(tone)}`}
                      >
                        {formatMetric(value, metric?.format ?? "number")}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
