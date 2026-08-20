"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, type ClientPortfolioDashboard } from "@/lib/api";
import { formatDate } from "@/lib/format";

function num(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

function pivotNum(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    maximumFractionDigits: 4,
    minimumFractionDigits: 2,
  });
}

const PRESELECT_KEY = "pivot-preselect-symbols";

export function ClientPortfolioView() {
  const [asOf, setAsOf] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const dashQuery = useQuery({
    queryKey: ["client-portfolio-dashboard", asOf ?? "latest"],
    queryFn: () => api.getClientPortfolioDashboard(asOf),
  });

  const data = dashQuery.data;
  const q = query.trim().toLowerCase();
  const holdings = useMemo(() => {
    const rows = data?.holdings ?? [];
    return q ? rows.filter((r) => r.symbol.toLowerCase().includes(q)) : rows;
  }, [data?.holdings, q]);

  const openInPivot = () => {
    const symbols = data?.model_symbols ?? [];
    if (symbols.length) {
      sessionStorage.setItem(PRESELECT_KEY, JSON.stringify(symbols));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            Strategy
          </p>
          <h2 className="text-2xl font-semibold text-stone-900">Client Portfolio</h2>
          <p className="mt-1 max-w-2xl text-sm text-stone-600">
            Quantities from Research <span className="font-medium">PMS_ClientPortfolio.xlsx</span>{" "}
            (Model). Prices, pivots, and Vol Exp from the last committed Pivot bhav day — upload
            bhav on Pivot Point Strategy.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-stone-600">
            As-of (bhav)
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
              {!data?.available_dates?.length ? (
                <option value="">No bhav days yet</option>
              ) : null}
            </select>
          </label>
          <Link
            href="/strategy/pivot-point"
            onClick={openInPivot}
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-800 hover:bg-stone-50"
          >
            Open in Pivot Daily
          </Link>
        </div>
      </div>

      {data?.error ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {data.error}
        </p>
      ) : null}

      {data && !data.error ? (
        <div className="flex flex-wrap gap-4 text-sm text-stone-600">
          <span>
            Excel total:{" "}
            <span className="font-medium text-stone-900">{num(data.excel_total_value, 0)}</span>
          </span>
          <span>
            Bhav revalued:{" "}
            <span className="font-medium text-stone-900">{num(data.bhav_revalued_total, 0)}</span>
          </span>
          {data.missing_symbols.length ? (
            <span className="text-amber-800">
              Missing bhav: {data.missing_symbols.length}
            </span>
          ) : null}
          {data.excel_mtime ? (
            <span className="text-stone-400">Workbook {data.excel_mtime}</span>
          ) : null}
        </div>
      ) : null}

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter by symbol…"
        className="w-full max-w-xs rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm shadow-sm outline-none ring-emerald-600/30 focus:ring-2"
      />

      {dashQuery.isLoading ? <p className="text-stone-600">Loading…</p> : null}
      {dashQuery.isError ? (
        <p className="text-red-700">{(dashQuery.error as Error).message}</p>
      ) : null}

      {data ? <HoldingsTable rows={holdings} /> : null}
    </div>
  );
}

function HoldingsTable({ rows }: { rows: ClientPortfolioDashboard["holdings"] }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-stone-700">
        Model holdings ({rows.length})
      </h3>
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.06em] text-stone-500">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2">Srs</th>
              <th className="px-3 py-2 text-right">Excel Px</th>
              <th className="px-3 py-2 text-right">Close</th>
              <th className="px-3 py-2 text-right">Excel Val</th>
              <th className="px-3 py-2 text-right">Bhav Val</th>
              <th className="px-3 py-2 text-right">%</th>
              <th className="px-3 py-2 text-right">S4-0.3</th>
              <th className="px-3 py-2 text-right">S1-03</th>
              <th className="px-3 py-2 text-right">Pivot</th>
              <th className="px-3 py-2 text-right">R1+0.3</th>
              <th className="px-3 py-2 text-right">R4+0.3</th>
              <th className="px-3 py-2 text-right">Vol Exp</th>
              <th className="px-3 py-2 text-right">15min</th>
              <th className="px-3 py-2">Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const p = row.pivot;
              const miss = row.missing_bhav || !p || p.missing;
              const flags: string[] = [];
              if (row.missing_bhav) flags.push("no bhav");
              if (row.be_only) flags.push("BE");
              if (row.qty_mismatch) flags.push("qty≠Stocks");
              return (
                <tr key={row.symbol} className="border-t border-stone-100">
                  <td className="px-3 py-1.5 font-medium">{row.symbol}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(row.qty, 0)}</td>
                  <td className="px-3 py-1.5">{row.series ?? "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(row.excel_price)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(row.close)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(row.excel_value, 0)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(row.bhav_value, 0)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {row.excel_percent == null ? "—" : num(row.excel_percent, 2)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {miss ? "—" : pivotNum(p?.s4_03)}
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
                    {miss ? "—" : pivotNum(p?.r4_03)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(row.vol_exp, 0)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{num(row.vol_15min, 0)}</td>
                  <td className="px-3 py-1.5 text-xs text-amber-800">
                    {flags.length ? flags.join(", ") : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
