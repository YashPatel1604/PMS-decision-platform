"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type ClientPortfolioDashboard,
  type ClientPortfolioYearlySeries,
} from "@/lib/api";
import { formatDate } from "@/lib/format";

function num(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function pct(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}%`;
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

const PRESELECT_KEY = "pivot-preselect-symbols";

export function ClientPortfolioView({
  book = "client",
}: {
  book?: "client" | "sca";
}) {
  const queryClient = useQueryClient();
  const [asOf, setAsOf] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [fetchMsg, setFetchMsg] = useState<string | null>(null);

  const dashQuery = useQuery({
    queryKey: ["client-portfolio-dashboard", book, asOf ?? "latest"],
    queryFn: () => api.getClientPortfolioDashboard(asOf, book),
  });

  const fetchNseMutation = useMutation({
    mutationFn: () => api.fetchNseBhav(),
    onSuccess: (result) => {
      setFetchMsg(result.message);
      setAsOf(result.trade_date);
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["pivot-dashboard"] });
    },
    onError: (err: Error) => setFetchMsg(apiDetail(err)),
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
          <h2 className="text-2xl font-semibold text-stone-900">
            {book === "sca" ? "SCA LLP Holdings" : "Client Portfolio"}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-stone-600">
            {book === "sca" ? (
              <>
                Qty from DailyEditFiles{" "}
                <span className="font-medium">SCA_LLP Stock Holding.xlsx</span>. Price,
                Value, Percent, and Total refresh from the as-of bhav day (qty × close).
                Ramprasath Reddy qty stays as typed in Excel; Qty − Ramprasath is D−H;
                Blocked Account is Ramprasath qty × as-of price.
              </>
            ) : (
              <>
                Qnty / Index / Mcap / Date / %Firm from Research{" "}
                <span className="font-medium">PMS_ClientPortfolio.xlsx</span>. Price, Value,
                Percent, and Total_Value refresh from the as-of bhav day (qty × close).
              </>
            )}
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
          <button
            type="button"
            disabled={fetchNseMutation.isPending}
            onClick={() => {
              setFetchMsg(null);
              fetchNseMutation.mutate();
            }}
            className="rounded-lg border border-emerald-700 bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {fetchNseMutation.isPending ? "Pulling NSE…" : "Pull today's bhav"}
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
          <Link
            href="/strategy/pivot-point"
            onClick={openInPivot}
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-800 hover:bg-stone-50"
          >
            Open in Pivot Daily
          </Link>
        </div>
      </div>

      {data?.as_of ? (
        <p className="text-sm text-stone-500">
          Marks from bhav{" "}
          <span className="font-medium text-stone-800">{formatDate(data.as_of)}</span>.
          Benchmark yearly tables stay from the workbook.
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

      {data?.error ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {data.error}
        </p>
      ) : null}

      {data && !data.error ? (
        <div className="flex flex-wrap gap-4 text-sm text-stone-600">
          <span>
            Total_Value:{" "}
            <span className="font-medium text-stone-900">
              {num(data.total_value ?? data.bhav_revalued_total)}
            </span>
          </span>
          {book === "sca" && data.portfolio_total != null ? (
            <span>
              Total Portfolio:{" "}
              <span className="font-medium text-stone-900">
                {num(data.portfolio_total)}
              </span>
            </span>
          ) : null}
          {data.missing_symbols.length ? (
            <span className="text-amber-800">
              Missing bhav: {data.missing_symbols.length}
            </span>
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

      {data ? (
        <ModelTable
          rows={holdings}
          total={data.total_value ?? data.bhav_revalued_total}
          book={book}
          bankBalance={data.bank_balance}
          portfolioTotal={data.portfolio_total}
        />
      ) : null}
      {data?.yearly?.length ? <YearlySection series={data.yearly} /> : null}
    </div>
  );
}

function ModelTable({
  rows,
  total,
  book,
  bankBalance,
  portfolioTotal,
}: {
  rows: ClientPortfolioDashboard["holdings"];
  total: number | null | undefined;
  book: "client" | "sca";
  bankBalance?: number | null;
  portfolioTotal?: number | null;
}) {
  const sca = book === "sca";
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(
    bankBalance != null && Number.isFinite(bankBalance) ? String(bankBalance) : "",
  );
  useEffect(() => {
    setDraft(
      bankBalance != null && Number.isFinite(bankBalance) ? String(bankBalance) : "",
    );
  }, [bankBalance]);

  const saveBank = useMutation({
    mutationFn: (amount: number) => api.patchScaBankBalance(amount),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
    },
  });

  const commitBank = () => {
    const parsed = Number(draft.replace(/,/g, ""));
    if (!Number.isFinite(parsed)) return;
    if (bankBalance != null && parsed === bankBalance) return;
    saveBank.mutate(parsed);
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-stone-700">
        {sca ? "Quantity" : "Model"} ({rows.length})
      </h3>
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.06em] text-stone-500">
            <tr>
              <th className="px-3 py-2">{sca ? "Symbol" : "Model"}</th>
              <th className="px-3 py-2 text-right">Qnty</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Value</th>
              <th className="px-3 py-2 text-right">Percent</th>
              {sca ? (
                <>
                  <th className="px-3 py-2 text-right">Qty − Ramprasath</th>
                  <th className="px-3 py-2 text-right">Ramprasath Reddy Qtyn</th>
                  <th className="px-3 py-2 text-right">Blocked Account</th>
                </>
              ) : (
                <>
                  <th className="px-3 py-2">Index</th>
                  <th className="px-3 py-2 text-right">Mcap</th>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2 text-right">%Firm</th>
                  <th className="px-3 py-2 text-right">Value</th>
                  <th className="px-3 py-2">Portfolio</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol} className="border-t border-stone-100">
                <td className="px-3 py-1.5 font-medium">{row.symbol}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{num(row.qty, 0)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {num(row.price ?? row.close ?? row.excel_price)}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {num(row.value ?? row.bhav_value ?? row.excel_value)}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {row.percent == null && row.excel_percent == null
                    ? "—"
                    : num(row.percent ?? row.excel_percent, 2)}
                </td>
                {sca ? (
                  <>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {num(row.ex_ramprasath_qty, 0)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {num(row.ramprasath_qty, 0)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {num(row.blocked_value)}
                    </td>
                  </>
                ) : (
                  <>
                    <td className="px-3 py-1.5">{row.index_label ?? "—"}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{num(row.mcap)}</td>
                    <td className="px-3 py-1.5 whitespace-nowrap">{row.as_of_label ?? "—"}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {row.firm_pct == null ? "—" : num(row.firm_pct, 2)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {num(row.target_value)}
                    </td>
                    <td className="px-3 py-1.5">{row.portfolio_flag ?? "—"}</td>
                  </>
                )}
              </tr>
            ))}
            {total != null ? (
              <tr className="border-t border-stone-200 bg-stone-50 font-medium">
                <td className="px-3 py-1.5">Total_Value</td>
                <td className="px-3 py-1.5" colSpan={2} />
                <td className="px-3 py-1.5 text-right tabular-nums">{num(total)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">100.00</td>
                <td className="px-3 py-1.5" colSpan={sca ? 3 : 6} />
              </tr>
            ) : null}
            {sca ? (
              <>
                <tr className="border-t border-stone-100">
                  <td className="px-3 py-1.5">Balance with Bank</td>
                  <td className="px-3 py-1.5" colSpan={2} />
                  <td className="px-3 py-1.5 text-right">
                    <input
                      type="text"
                      inputMode="decimal"
                      aria-label="Balance with Bank"
                      value={draft}
                      disabled={saveBank.isPending}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={commitBank}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.currentTarget.blur();
                        }
                      }}
                      className="w-36 rounded border border-stone-200 bg-white px-2 py-1 text-right tabular-nums outline-none ring-emerald-600/30 focus:ring-2"
                    />
                  </td>
                  <td className="px-3 py-1.5" colSpan={4} />
                </tr>
                <tr className="border-t border-stone-200 bg-stone-50 font-medium">
                  <td className="px-3 py-1.5">Total Portfolio Value</td>
                  <td className="px-3 py-1.5" colSpan={2} />
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {num(
                      portfolioTotal ??
                        (total ?? 0) + (Number(draft.replace(/,/g, "")) || 0),
                    )}
                  </td>
                  <td className="px-3 py-1.5" colSpan={4} />
                </tr>
              </>
            ) : null}
          </tbody>
        </table>
      </div>
      {saveBank.isError ? (
        <p className="text-sm text-red-700">{(saveBank.error as Error).message}</p>
      ) : null}
    </div>
  );
}


function YearlySection({ series }: { series: ClientPortfolioYearlySeries[] }) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-stone-700">Yearly returns</h3>
      <div className="grid gap-4 xl:grid-cols-2">
        {series.map((block) => (
          <YearlyTable key={block.name} block={block} />
        ))}
      </div>
    </div>
  );
}

function YearlyTable({ block }: { block: ClientPortfolioYearlySeries }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.06em] text-stone-500">
          <tr>
            <th className="px-3 py-2" colSpan={5}>
              {block.name}
            </th>
          </tr>
          <tr>
            <th className="px-3 py-2">Year</th>
            <th className="px-3 py-2 text-right">Start</th>
            <th className="px-3 py-2 text-right">End</th>
            <th className="px-3 py-2 text-right">Return</th>
            <th className="px-3 py-2 text-right">Cum</th>
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row) => (
            <tr key={row.year} className="border-t border-stone-100">
              <td className="px-3 py-1.5 tabular-nums">{row.year}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{num(row.start)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{num(row.end)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{pct(row.return_pct)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{pct(row.cum_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
