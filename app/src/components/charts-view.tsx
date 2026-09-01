"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type ChartsDashboard, type ChartsRangeRow } from "@/lib/api";
import { DailyEditPanel } from "@/components/daily-edit-panel";
import { formatDate } from "@/lib/format";

const CORR_KEY = "charts-corr-pcts";

function loadCorrPcts(): { a: number; b: number } {
  try {
    const raw = localStorage.getItem(CORR_KEY);
    if (!raw) return { a: 10, b: 20 };
    const parsed = JSON.parse(raw) as { a?: unknown; b?: unknown };
    const a = Number(parsed.a);
    const b = Number(parsed.b);
    return {
      a: Number.isFinite(a) ? Math.min(20, Math.max(1, Math.round(a))) : 10,
      b: Number.isFinite(b) ? Math.min(20, Math.max(1, Math.round(b))) : 20,
    };
  } catch {
    return { a: 10, b: 20 };
  }
}

function num(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function pct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}%`;
}

function apiDetail(err: Error): string {
  try {
    const parsed = JSON.parse(err.message) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    /* plain */
  }
  return err.message;
}

function parseNum(raw: string): number | null {
  const trimmed = raw.trim().replace(/,/g, "");
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

/** Live fib / corr / % from lows from editable High / Low / Close. */
function derive(
  high: number | null,
  low: number | null,
  close: number | null,
  corrA: number,
  corrB: number,
) {
  const difference = high != null && low != null ? high - low : null;
  const trg = (frac: number) =>
    difference != null && low != null ? difference * frac + low : null;
  const trg_13 = trg(0.13);
  const trg_89 = trg(0.89);
  const pct_from_lows =
    close != null && low != null && low !== 0 ? (close * 100) / low - 100 : null;
  const corr = (pct: number) =>
    high != null && close != null ? high - close * (pct / 100) : null;
  return {
    difference,
    trg_13,
    trg_21: trg(0.21),
    trg_34: trg(0.34),
    trg_55: trg(0.55),
    trg_89,
    trg_144: trg_13 != null && difference != null ? trg_13 * 1.44 + difference : null,
    pct_from_lows,
    corr_a: corr(corrA),
    corr_b: corr(corrB),
    below_trg_89: close != null && trg_89 != null && close < trg_89,
    below_low: close != null && low != null && close < low,
    above_high: close != null && high != null && close > high,
  };
}

export function ChartsView() {
  const queryClient = useQueryClient();
  const [asOf, setAsOf] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [fetchMsg, setFetchMsg] = useState<string | null>(null);
  const [corrPcts, setCorrPcts] = useState(loadCorrPcts);

  useEffect(() => {
    try {
      localStorage.setItem(CORR_KEY, JSON.stringify(corrPcts));
    } catch {
      /* ignore */
    }
  }, [corrPcts]);

  const dashQuery = useQuery({
    queryKey: ["charts-dashboard", asOf ?? "latest"],
    queryFn: () => api.getChartsDashboard(asOf),
  });
  const data = dashQuery.data;

  const fetchNse = useMutation({
    mutationFn: () => api.fetchNseBhav(),
    onSuccess: (result) => {
      setFetchMsg(result.message);
      setAsOf(result.trade_date);
      void queryClient.invalidateQueries({ queryKey: ["charts-dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["pivot-dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
    },
    onError: (err: Error) => setFetchMsg(apiDetail(err)),
  });

  const q = query.trim().toLowerCase();
  const { holdings, fno } = useMemo(() => {
    const all = data?.rows ?? [];
    const match = all.filter(
      (r) =>
        !q ||
        r.symbol.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q),
    );
    return {
      holdings: match.filter((r) => r.section !== "fno"),
      fno: match.filter((r) => r.section === "fno"),
    };
  }, [data?.rows, q]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            Strategy
          </p>
          <h2 className="text-2xl font-semibold text-stone-900">Charts</h2>
          <p className="mt-1 max-w-2xl text-sm text-stone-600">
            Range from DailyEditFiles <span className="font-medium">Charts.xlsx</span>.
            High / Low / Close are editable (writes Excel or shared DB when cloud mode is on).
            Corr bands use the sliders below (personal — saved on this device). Close below Low →
            red; above High → blue.
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
            disabled={fetchNse.isPending}
            onClick={() => {
              setFetchMsg(null);
              fetchNse.mutate();
            }}
            className="rounded-lg border border-emerald-700 bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {fetchNse.isPending ? "Pulling NSE…" : "Pull today's bhav"}
          </button>
        </div>
      </div>

      {data?.approval_workflow ? <DailyEditPanel category="charts" /> : null}

      {data?.as_of ? (
        <p className="text-sm text-stone-500">
          Marks from bhav{" "}
          <span className="font-medium text-stone-800">{formatDate(data.as_of)}</span>
          . Edit High / Low / Close then blur to save. Weekly S/R on holdings only.
        </p>
      ) : null}

      <div className="flex flex-wrap gap-6 rounded-xl border border-stone-200 bg-white px-4 py-3">
        <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-sm text-stone-600">
          <span className="flex justify-between">
            <span>Corr A</span>
            <span className="font-medium tabular-nums text-stone-900">{corrPcts.a}%</span>
          </span>
          <input
            type="range"
            min={1}
            max={20}
            step={1}
            value={corrPcts.a}
            onChange={(e) =>
              setCorrPcts((prev) => ({ ...prev, a: Number(e.target.value) }))
            }
            className="w-full accent-emerald-700"
          />
        </label>
        <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-sm text-stone-600">
          <span className="flex justify-between">
            <span>Corr B</span>
            <span className="font-medium tabular-nums text-stone-900">{corrPcts.b}%</span>
          </span>
          <input
            type="range"
            min={1}
            max={20}
            step={1}
            value={corrPcts.b}
            onChange={(e) =>
              setCorrPcts((prev) => ({ ...prev, b: Number(e.target.value) }))
            }
            className="w-full accent-emerald-700"
          />
        </label>
      </div>

      {fetchMsg ? (
        <p
          className={`rounded-lg border px-3 py-2 text-sm ${
            fetchNse.isError
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

      {data && !data.error && data.missing_symbols.length ? (
        <p className="text-sm text-amber-800">
          Missing bhav: {data.missing_symbols.length}
        </p>
      ) : null}

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter by name…"
        className="w-full max-w-xs rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm shadow-sm outline-none ring-emerald-600/30 focus:ring-2"
      />

      {dashQuery.isLoading ? <p className="text-stone-600">Loading…</p> : null}
      {dashQuery.isError ? (
        <p className="text-red-700">{(dashQuery.error as Error).message}</p>
      ) : null}

      {data ? (
        <>
          <RangeTable
            title="Holdings"
            rows={holdings}
            weekly
            corrA={corrPcts.a}
            corrB={corrPcts.b}
          />
          <RangeTable
            title="NIFTY FNO STOCKS"
            rows={fno}
            corrA={corrPcts.a}
            corrB={corrPcts.b}
          />
        </>
      ) : null}
    </div>
  );
}

function RangeTable({
  title,
  rows,
  weekly = false,
  corrA,
  corrB,
}: {
  title: string;
  rows: ChartsDashboard["rows"];
  weekly?: boolean;
  corrA: number;
  corrB: number;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-stone-700">
        {title}
        <span className="ml-2 font-normal normal-case tracking-normal text-stone-500">
          {rows.length}
        </span>
      </h3>
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.06em] text-stone-500">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2 text-right">High</th>
              <th className="px-3 py-2 text-right">Low</th>
              <th className="px-3 py-2 text-right">Diff</th>
              <th className="px-3 py-2 text-right">Trg 13</th>
              <th className="px-3 py-2 text-right">Trg 21</th>
              <th className="px-3 py-2 text-right">Trg 34</th>
              <th className="px-3 py-2 text-right">Trg 55</th>
              <th className="px-3 py-2 text-right">Trg 89</th>
              <th className="px-3 py-2 text-right">Trg 144</th>
              <th className="px-3 py-2 text-right">% from lows</th>
              <th className="px-3 py-2 text-right">Close</th>
              <th className="px-3 py-2 text-right">Prev close</th>
              <th className="px-3 py-2 text-right">{corrA}% corr</th>
              <th className="px-3 py-2 text-right">{corrB}% corr</th>
              {weekly ? (
                <>
                  <th className="px-3 py-2 text-right">Weekly close</th>
                  <th className="px-3 py-2">S / R</th>
                  <th className="px-3 py-2">Weekly date</th>
                </>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <RangeRow
                key={`${row.section}-${row.excel_row}`}
                row={row}
                weekly={weekly}
                corrA={corrA}
                corrB={corrB}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const cellInput =
  "w-full min-w-[5rem] rounded border border-stone-200 bg-white px-1.5 py-1 text-sm tabular-nums outline-none ring-emerald-600/30 focus:ring-2";

function RangeRow({
  row,
  weekly,
  corrA,
  corrB,
}: {
  row: ChartsRangeRow;
  weekly: boolean;
  corrA: number;
  corrB: number;
}) {
  const queryClient = useQueryClient();
  const [high, setHigh] = useState(row.high != null ? String(row.high) : "");
  const [low, setLow] = useState(row.low != null ? String(row.low) : "");
  const [close, setClose] = useState(row.close != null ? String(row.close) : "");
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setHigh(row.high != null ? String(row.high) : "");
    setLow(row.low != null ? String(row.low) : "");
    setClose(row.close != null ? String(row.close) : "");
  }, [row.excel_row, row.high, row.low, row.close]);

  const highN = parseNum(high);
  const lowN = parseNum(low);
  const closeN = parseNum(close);
  const d = derive(highN, lowN, closeN, corrA, corrB);

  const save = useMutation({
    mutationFn: (body: { high?: number; low?: number; close?: number }) =>
      api.patchChartsLevels({ excel_row: row.excel_row, ...body }),
    onSuccess: () => {
      setSaveError(null);
      void queryClient.invalidateQueries({ queryKey: ["charts-dashboard"] });
    },
    onError: (err: Error) => setSaveError(apiDetail(err)),
  });

  const commitField = (field: "high" | "low" | "close", raw: string, original: number | null) => {
    const parsed = parseNum(raw);
    if (raw.trim() !== "" && parsed == null) {
      setSaveError(`${field} must be a number`);
      return;
    }
    if (parsed == null) return;
    if (original != null && parsed === original) return;
    save.mutate({ [field]: parsed });
  };

  const rowTone = d.below_low
    ? "bg-red-50"
    : d.above_high
      ? "bg-blue-50"
      : d.below_trg_89
        ? "bg-amber-50"
        : "";

  return (
    <tr className={`border-t border-stone-100 ${rowTone}`}>
      <td className="px-3 py-1.5 font-medium">
        {row.name}
        {row.missing_bhav ? (
          <span className="ml-2 text-xs font-normal text-amber-700">no bhav</span>
        ) : null}
        {saveError ? (
          <span className="ml-2 text-xs font-normal text-red-700">{saveError}</span>
        ) : null}
      </td>
      <td className="px-1 py-1">
        <input
          className={`${cellInput} text-right`}
          value={high}
          onChange={(e) => setHigh(e.target.value)}
          onBlur={() => commitField("high", high, row.high)}
          inputMode="decimal"
          aria-label={`${row.name} high`}
        />
      </td>
      <td className="px-1 py-1">
        <input
          className={`${cellInput} text-right`}
          value={low}
          onChange={(e) => setLow(e.target.value)}
          onBlur={() => commitField("low", low, row.low)}
          inputMode="decimal"
          aria-label={`${row.name} low`}
        />
      </td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.difference)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.trg_13)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.trg_21)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.trg_34)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.trg_55)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.trg_89)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.trg_144)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{pct(d.pct_from_lows)}</td>
      <td className="px-1 py-1">
        <input
          className={`${cellInput} text-right ${
            d.below_low ? "text-red-700" : d.above_high ? "text-blue-700" : ""
          }`}
          value={close}
          onChange={(e) => setClose(e.target.value)}
          onBlur={() => commitField("close", close, row.close)}
          inputMode="decimal"
          aria-label={`${row.name} close`}
        />
      </td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(row.prev_close)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.corr_a)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{num(d.corr_b)}</td>
      {weekly ? <WeeklyCells row={row} /> : null}
    </tr>
  );
}

function WeeklyCells({ row }: { row: ChartsRangeRow }) {
  const queryClient = useQueryClient();
  const [close, setClose] = useState(
    row.weekly_close != null && Number.isFinite(row.weekly_close) ? String(row.weekly_close) : "",
  );
  const [sr, setSr] = useState(row.support_resistance ?? "");
  const [wkDate, setWkDate] = useState(row.weekly_close_date ?? "");

  useEffect(() => {
    setClose(
      row.weekly_close != null && Number.isFinite(row.weekly_close) ? String(row.weekly_close) : "",
    );
    setSr(row.support_resistance ?? "");
    setWkDate(row.weekly_close_date ?? "");
  }, [row.excel_row, row.weekly_close, row.support_resistance, row.weekly_close_date]);

  const save = useMutation({
    mutationFn: () => {
      const trimmed = close.trim();
      const parsed = trimmed === "" ? null : Number(trimmed.replace(/,/g, ""));
      if (trimmed !== "" && !Number.isFinite(parsed)) {
        throw new Error("Weekly close must be a number");
      }
      return api.patchChartsWeekly({
        excel_row: row.excel_row,
        weekly_close: parsed,
        support_resistance: sr.trim() || null,
        weekly_close_date: wkDate.trim() || null,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["charts-dashboard"] });
    },
  });

  const commit = () => {
    const trimmed = close.trim();
    const parsed = trimmed === "" ? null : Number(trimmed.replace(/,/g, ""));
    if (trimmed !== "" && !Number.isFinite(parsed)) return;
    const sameClose =
      (parsed == null && row.weekly_close == null) ||
      (parsed != null && row.weekly_close != null && parsed === row.weekly_close);
    if (
      sameClose &&
      (sr.trim() || null) === (row.support_resistance || null) &&
      (wkDate.trim() || null) === (row.weekly_close_date || null)
    ) {
      return;
    }
    save.mutate();
  };

  return (
    <>
      <td className="px-1 py-1">
        <input
          className={`${cellInput} text-right`}
          value={close}
          onChange={(e) => setClose(e.target.value)}
          onBlur={commit}
          inputMode="decimal"
          aria-label={`${row.name} weekly close`}
        />
      </td>
      <td className="px-1 py-1">
        <input
          className={cellInput}
          value={sr}
          onChange={(e) => setSr(e.target.value)}
          onBlur={commit}
          aria-label={`${row.name} support resistance`}
        />
      </td>
      <td className="px-1 py-1">
        <input
          className={cellInput}
          value={wkDate}
          onChange={(e) => setWkDate(e.target.value)}
          onBlur={commit}
          aria-label={`${row.name} weekly close date`}
        />
      </td>
    </>
  );
}
