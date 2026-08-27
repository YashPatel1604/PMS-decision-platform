"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  api,
  type CompareSeries,
  type YahooSearchHit,
} from "@/lib/api";
import {
  formatDate,
  formatDays,
  formatInr,
  formatNum,
  formatPct,
  formatPnL,
  formatPp,
  formatPrice,
  toneClass,
  valueTone,
} from "@/lib/format";

function shiftMonths(iso: string, months: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setMonth(d.getMonth() + months);
  return d.toISOString().slice(0, 10);
}

function priorYearEndIso(iso: string): string {
  const year = Number(iso.slice(0, 4));
  return `${year - 1}-12-31`;
}

function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  return (
    <div className="min-w-0 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-stone-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${tone ? toneClass(tone) : ""}`}>
        {value}
      </p>
      {detail ? <p className="mt-1 text-sm text-stone-500">{detail}</p> : null}
    </div>
  );
}

type RangePreset = "since_entry" | "3m" | "6m" | "ytd" | "custom";

const BASE_SERIES = [
  { key: "stock" as const, label: "Stock", color: "#047857" },
  { key: "portfolio" as const, label: "Portfolio", color: "#a16207" },
  { key: "bse_smallcap" as const, label: "BSE SmallCap", color: "#1d4ed8" },
  { key: "industry_ew" as const, label: "Industry EW", color: "#7c3aed" },
];

const PEER_COLORS = [
  "#be123c",
  "#c2410c",
  "#0f766e",
  "#0369a1",
  "#a21caf",
  "#4d7c0f",
];

const MAX_PEERS = PEER_COLORS.length;

function peerColor(index: number): string {
  return PEER_COLORS[index % PEER_COLORS.length]!;
}

function CompareChart({ series }: { series: CompareSeries }) {
  const width = 420;
  const height = 200;
  const pad = 28;
  const points = series.points;
  if (points.length < 2) {
    return <p className="text-sm text-stone-500">Not enough points for a chart.</p>;
  }

  const peerTickers =
    series.peer_series?.map((p) => p.ticker) ??
    (series.peer_ticker ? [series.peer_ticker] : []);

  const seriesKeys: { key: string; label: string; color: string; peer?: boolean }[] = [
    ...BASE_SERIES,
    ...peerTickers.map((ticker, index) => ({
      key: `peer:${ticker}`,
      label: ticker,
      color: peerColor(index),
      peer: true,
    })),
  ];

  const valueAt = (p: (typeof points)[number], key: string): number | null => {
    if (key.startsWith("peer:")) {
      const ticker = key.slice(5);
      const fromMap = p.peers?.[ticker];
      if (fromMap != null) return fromMap;
      if (series.peer_ticker === ticker) return p.peer;
      return null;
    }
    return p[key as keyof typeof p] as number | null;
  };

  const values: number[] = [];
  for (const p of points) {
    for (const { key } of seriesKeys) {
      const v = valueAt(p, key);
      if (v != null) values.push(v);
    }
  }
  const minV = Math.min(...values, 90);
  const maxV = Math.max(...values, 110);
  const span = Math.max(maxV - minV, 1);

  const xAt = (i: number) => pad + (i / (points.length - 1)) * (width - pad * 2);
  const yAt = (v: number) => pad + (1 - (v - minV) / span) * (height - pad * 2);

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full">
        <line
          x1={pad}
          y1={height - pad}
          x2={width - pad}
          y2={height - pad}
          stroke="#e7e5e4"
        />
        <line x1={pad} y1={pad} x2={pad} y2={height - pad} stroke="#e7e5e4" />
        {seriesKeys.map(({ key, color }) => {
          const cmds: string[] = [];
          let started = false;
          points.forEach((p, i) => {
            const v = valueAt(p, key);
            // Keep the path open across gaps so start→end peer/industry lines still draw.
            if (v == null) return;
            cmds.push(`${started ? "L" : "M"}${xAt(i)} ${yAt(v)}`);
            started = true;
          });
          if (cmds.length < 2) return null;
          return (
            <path key={key} d={cmds.join(" ")} fill="none" stroke={color} strokeWidth={1.75} />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-stone-600">
        {seriesKeys.map(({ key, label, color }) => (
          <span key={key} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function HoldingsView() {
  const [asOf, setAsOf] = useState<string>("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toTouched, setToTouched] = useState(false);
  const [preset, setPreset] = useState<RangePreset>("since_entry");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [peerQuery, setPeerQuery] = useState("");
  const [peerHits, setPeerHits] = useState<YahooSearchHit[]>([]);
  const [peerTickers, setPeerTickers] = useState<string[]>([]);
  const effectiveFrom = fromDate.trim() || null;

  const holdingsQuery = useQuery({
    queryKey: ["open-holdings", toTouched ? asOf || "none" : "latest", effectiveFrom],
    queryFn: () => api.getOpenHoldings(toTouched ? asOf || null : null, effectiveFrom),
    staleTime: 60 * 1000,
  });

  useEffect(() => {
    const ceiling = holdingsQuery.data?.as_of_date;
    if (!ceiling) return;
    if (!toTouched || !asOf) {
      setAsOf(ceiling);
    }
  }, [holdingsQuery.data?.as_of_date, toTouched, asOf]);

  // If user picked a To past the ceiling, pull it back.
  useEffect(() => {
    const capped = holdingsQuery.data?.as_of_date;
    if (toTouched && capped && asOf && capped < asOf) {
      setAsOf(capped);
    }
  }, [holdingsQuery.data?.as_of_date, asOf, toTouched]);

  const selected = useMemo(
    () => holdingsQuery.data?.holdings.find((h) => h.episode_id === selectedId) ?? null,
    [holdingsQuery.data, selectedId],
  );

  useEffect(() => {
    if (!selectedId && holdingsQuery.data?.holdings.length) {
      setSelectedId(holdingsQuery.data.holdings[0].episode_id);
    }
  }, [holdingsQuery.data, selectedId]);

  const industryQuery = useQuery({
    queryKey: ["industry-compare", selectedId, asOf, effectiveFrom],
    queryFn: () => api.getIndustryCompare(selectedId!, asOf, effectiveFrom),
    enabled: selectedId != null && Boolean(asOf),
  });

  const seriesQuery = useQuery({
    queryKey: ["compare-series", selectedId, asOf, effectiveFrom, peerTickers],
    queryFn: () => api.getCompareSeries(selectedId!, asOf, effectiveFrom, peerTickers),
    enabled: selectedId != null && Boolean(asOf),
  });

  const peerFrom =
    effectiveFrom ?? selected?.period_start_date ?? selected?.entry_date ?? null;

  useEffect(() => {
    if (peerQuery.trim().length < 2) {
      setPeerHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void api
        .searchYahoo(peerQuery.trim())
        .then(setPeerHits)
        .catch(() => setPeerHits([]));
    }, 300);
    return () => window.clearTimeout(handle);
  }, [peerQuery]);

  const applyPreset = (next: RangePreset) => {
    setPreset(next);
    if (next === "since_entry") {
      setFromDate("");
      return;
    }
    if (!asOf) return;
    if (next === "3m") {
      setFromDate(shiftMonths(asOf, -3));
      return;
    }
    if (next === "6m") {
      setFromDate(shiftMonths(asOf, -6));
      return;
    }
    if (next === "ytd") {
      setFromDate(priorYearEndIso(asOf));
    }
  };

  const filtered = useMemo(() => {
    const rows = holdingsQuery.data?.holdings ?? [];
    if (!query.trim()) return rows;
    const needle = query.toLowerCase();
    return rows.filter(
      (row) =>
        row.portfolio_name.toLowerCase().includes(needle) ||
        row.security_id.toLowerCase().includes(needle) ||
        (row.industry ?? "").toLowerCase().includes(needle),
    );
  }, [holdingsQuery.data, query]);

  if (holdingsQuery.isLoading) {
    return <p className="text-stone-600">Loading open holdings…</p>;
  }

  if (holdingsQuery.isError || !holdingsQuery.data) {
    const err = holdingsQuery.error as Error | null;
    let detail = err?.message ?? "";
    try {
      const parsed = JSON.parse(detail) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* plain text */
    }
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-900">
        <p className="font-semibold">Could not load holdings.</p>
        <p className="mt-2 text-sm">
          Confirm the API is running and market prices are imported, then refresh.
        </p>
        {detail ? (
          <p className="mt-3 break-words rounded bg-red-100/80 px-3 py-2 font-mono text-xs text-red-950">
            {detail}
          </p>
        ) : null}
        <button
          type="button"
          className="mt-4 rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white"
          onClick={() => void holdingsQuery.refetch()}
        >
          Retry
        </button>
      </div>
    );
  }

  const data = holdingsQuery.data;
  const bookDate = data.portfolio_value_observation_date ?? data.as_of_date;
  const periodLabel = data.from_date
    ? `${formatDate(data.from_date)} → ${formatDate(data.as_of_date)}`
    : `Entry → ${formatDate(data.as_of_date)}`;

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            Current book
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Holdings analyze</h1>
          <p className="mt-3 text-base leading-7 text-stone-600">
            Pick a From date to reprice every open name over that window (start
            and now price, Stock %). Portfolio totals above are the book; the
            table is per holding. Qty and Mcap follow Model when present.
          </p>
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["since_entry", "Since entry"],
                ["3m", "Last 3M"],
                ["6m", "Last 6M"],
                ["ytd", "YTD"],
                ["custom", "Custom"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => applyPreset(key)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  preset === key
                    ? "bg-emerald-700 text-white"
                    : "bg-white text-stone-700 ring-1 ring-stone-200 hover:bg-stone-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex flex-col gap-1 text-sm text-stone-600">
              From
              <input
                type="date"
                value={fromDate}
                max={asOf || undefined}
                onChange={(event) => {
                  setFromDate(event.target.value);
                  setPreset(event.target.value ? "custom" : "since_entry");
                }}
                className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-200"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-stone-600">
              To (as-of)
              <input
                type="date"
                value={asOf}
                max={bookDate}
                onChange={(event) => {
                  const next = event.target.value;
                  setToTouched(true);
                  setAsOf(next);
                  if (preset === "3m") setFromDate(shiftMonths(next, -3));
                  if (preset === "6m") setFromDate(shiftMonths(next, -6));
                  if (preset === "ytd") setFromDate(priorYearEndIso(next));
                }}
                className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-200"
              />
            </label>
          </div>
        </div>
      </header>

      <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
        <div
          className={`grid divide-y divide-stone-200 border-y border-stone-200 sm:divide-x sm:divide-y-0 ${
            data.from_date ? "sm:grid-cols-3" : "sm:grid-cols-2"
          }`}
        >
          <div className={data.from_date ? "sm:pr-4" : "sm:pr-6"}>
            <Metric
              label="Open holdings"
              value={String(data.open_count)}
              detail={`Period ${periodLabel}`}
            />
          </div>
          {data.from_date ? (
            <div className="sm:px-4">
              <Metric
                label="Portfolio value"
                value={formatInr(data.equity_market_value_from)}
                detail={[
                  formatDate(data.from_date),
                  data.portfolio_value_from_source
                    ? `src ${data.portfolio_value_from_source}`
                    : null,
                  data.portfolio_value_from_check_delta != null
                    ? `vs rebuild ${formatInr(data.reconstructed_equity_market_value_from)} (Δ ${formatInr(data.portfolio_value_from_check_delta)})`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              />
            </div>
          ) : null}
          <div className={data.from_date ? "sm:pl-4" : "sm:pl-6"}>
            <Metric
              label="Portfolio value"
              value={formatInr(data.equity_market_value)}
              detail={[
                formatDate(data.as_of_date),
                data.portfolio_value_source ? `src ${data.portfolio_value_source}` : null,
                data.portfolio_value_check_delta != null
                  ? `vs rebuild ${formatInr(data.reconstructed_equity_market_value)} (Δ ${formatInr(data.portfolio_value_check_delta)})`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            />
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] xl:items-start">
        <section className="space-y-4 min-w-0">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Open positions</h2>
              <p className="mt-2 text-sm text-stone-600">
                Click a row for the compare panel. Portfolio comparator is provisional.
              </p>
            </div>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search stocks"
              className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-200"
            />
          </div>

          <div className="max-h-[min(70vh,52rem)] overflow-auto rounded-xl border border-stone-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 z-10 border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-3 py-3 font-semibold">Stock</th>
                  <th className="px-3 py-3 font-semibold">Period</th>
                  {data.from_date ? (
                    <>
                      <th className="px-3 py-3 text-right font-semibold">Start</th>
                      <th className="px-3 py-3 text-right font-semibold">Now</th>
                    </>
                  ) : null}
                  <th className="px-3 py-3 text-right font-semibold">Stock %</th>
                  <th className="px-3 py-3 text-right font-semibold">Port %</th>
                  <th className="px-3 py-3 text-right font-semibold">vs Port</th>
                  <th className="px-3 py-3 text-right font-semibold">BSE %</th>
                  <th className="px-3 py-3 text-right font-semibold">vs BSE</th>
                  <th className="px-3 py-3 text-right font-semibold">Mcap</th>
                  <th className="px-3 py-3 text-right font-semibold">Wt %</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => {
                  const active = row.episode_id === selectedId;
                  return (
                    <tr
                      key={row.episode_id}
                      onClick={() => setSelectedId(row.episode_id)}
                      className={`cursor-pointer border-b border-stone-100 align-top last:border-0 ${
                        active ? "bg-emerald-50/70" : "hover:bg-stone-50"
                      }`}
                    >
                      <td className="px-3 py-3">
                        <Link
                          href={`/episodes/${row.episode_id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="font-medium text-emerald-800 underline-offset-4 hover:underline"
                        >
                          {row.portfolio_name}
                        </Link>
                        <p className="text-xs text-stone-500">
                          {row.industry ?? row.sector ?? row.security_id}
                        </p>
                      </td>
                      <td className="px-3 py-3">
                        <p className="text-xs">
                          {formatDate(row.period_start_date)} → {formatDate(row.as_of_date)}
                        </p>
                        <p className="text-xs text-stone-500">{formatDays(row.period_days)}</p>
                      </td>
                      {data.from_date ? (
                        <>
                          <td className="px-3 py-3 text-right tabular-nums">
                            {formatPrice(row.from_price)}
                          </td>
                          <td className="px-3 py-3 text-right tabular-nums">
                            {formatPrice(row.as_of_price)}
                          </td>
                        </>
                      ) : null}
                      <td
                        className={`px-3 py-3 text-right font-medium tabular-nums ${toneClass(
                          valueTone(row.stock_return_pct),
                        )}`}
                      >
                        {formatPct(row.stock_return_pct)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {formatPct(row.portfolio_return_pct)}
                      </td>
                      <td
                        className={`px-3 py-3 text-right font-medium tabular-nums ${toneClass(
                          valueTone(row.excess_vs_portfolio_pp),
                        )}`}
                      >
                        {formatPp(row.excess_vs_portfolio_pp)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {formatPct(row.bse_return_pct)}
                      </td>
                      <td
                        className={`px-3 py-3 text-right font-medium tabular-nums ${toneClass(
                          valueTone(row.excess_vs_bse_pp),
                        )}`}
                      >
                        {formatPp(row.excess_vs_bse_pp)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {row.mcap == null ? "—" : formatNum(row.mcap)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {formatPct(row.position_weight_pct)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filtered.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-stone-500">No matches.</p>
            ) : null}
          </div>
        </section>

        <aside className="space-y-4 rounded-2xl border border-stone-200 bg-white p-5 shadow-sm xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto xl:self-start">
          {!selected ? (
            <p className="text-sm text-stone-500">Select a holding to compare.</p>
          ) : (
            <>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700">
                  Compare panel
                </p>
                <h3 className="mt-1 text-xl font-semibold">{selected.portfolio_name}</h3>
                <p className="text-sm text-stone-500">
                  {formatDate(selected.period_start_date)} → {formatDate(selected.as_of_date)}
                  {selected.industry ? ` · ${selected.industry}` : ""}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs text-stone-500">Stock</p>
                  <p className={`font-semibold tabular-nums ${toneClass(valueTone(selected.stock_return_pct))}`}>
                    {formatPct(selected.stock_return_pct)}
                  </p>
                  {data.from_date ? (
                    <p className="mt-1 text-xs text-stone-500">
                      Period start{" "}
                      <span className="tabular-nums text-stone-700">
                        {formatPrice(selected.from_price)}
                      </span>
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-stone-500">
                      1st buy{" "}
                      <span className="tabular-nums text-stone-700">
                        {formatPrice(selected.first_buy_price)}
                      </span>
                    </p>
                  )}
                  <p className="text-xs text-stone-500">
                    Avg buy{" "}
                    <span className="tabular-nums text-stone-700">
                      {formatPrice(selected.average_buy_price)}
                    </span>
                  </p>
                  <p className="text-xs text-stone-500">
                    Current{" "}
                    <span className="tabular-nums text-stone-700">
                      {formatPrice(selected.as_of_price)}
                    </span>
                  </p>
                </div>
                <div>
                  <p className="text-xs text-stone-500">Portfolio (prov.)</p>
                  <p className="font-semibold tabular-nums">
                    {formatPct(selected.portfolio_return_pct)}
                  </p>
                  <p className={`text-xs tabular-nums ${toneClass(valueTone(selected.excess_vs_portfolio_pp))}`}>
                    Excess {formatPp(selected.excess_vs_portfolio_pp)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-stone-500">BSE SmallCap</p>
                  <p className="font-semibold tabular-nums">{formatPct(selected.bse_return_pct)}</p>
                  <p className={`text-xs tabular-nums ${toneClass(valueTone(selected.excess_vs_bse_pp))}`}>
                    Excess {formatPp(selected.excess_vs_bse_pp)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-stone-500">Industry EW</p>
                  <p className="font-semibold tabular-nums">
                    {formatPct(industryQuery.data?.total_return_pct ?? null)}
                  </p>
                  <p className="text-xs text-stone-500">
                    {industryQuery.data
                      ? `${industryQuery.data.used_count}/${industryQuery.data.peer_count} peers`
                      : "—"}
                  </p>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-stone-500">
                  Peer stocks (Yahoo / BSE)
                </p>
                <input
                  value={peerQuery}
                  onChange={(e) => setPeerQuery(e.target.value)}
                  placeholder={
                    peerTickers.length >= MAX_PEERS
                      ? `Max ${MAX_PEERS} peers`
                      : "Add symbol or name…"
                  }
                  disabled={peerTickers.length >= MAX_PEERS}
                  className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:bg-stone-50"
                />
                {peerHits.length > 0 ? (
                  <ul className="mt-1 max-h-40 overflow-auto rounded-lg border border-stone-200 bg-white text-sm shadow-sm">
                    {peerHits.map((hit) => (
                      <li key={hit.yahoo_ticker}>
                        <button
                          type="button"
                          className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left hover:bg-stone-50 disabled:opacity-40"
                          disabled={peerTickers.includes(hit.yahoo_ticker)}
                          onClick={() => {
                            setPeerTickers((prev) =>
                              prev.includes(hit.yahoo_ticker) || prev.length >= MAX_PEERS
                                ? prev
                                : [...prev, hit.yahoo_ticker],
                            );
                            setPeerQuery("");
                            setPeerHits([]);
                          }}
                        >
                          <span>
                            <span className="font-medium">{hit.symbol}</span>
                            <span className="mt-0.5 block text-xs text-stone-500">{hit.name}</span>
                          </span>
                          <span className="text-xs text-stone-400">{hit.exchange}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {peerTickers.length > 0 ? (
                  <ul className="mt-2 space-y-1.5">
                    {peerTickers.map((ticker, index) => {
                      const summary = seriesQuery.data?.peer_series?.find(
                        (p) => p.ticker === ticker,
                      );
                      return (
                        <li
                          key={ticker}
                          className="flex flex-wrap items-center gap-2 text-sm"
                        >
                          <span
                            className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                            style={{ background: peerColor(index) }}
                          />
                          <span className="font-medium">{ticker}</span>
                          <span
                            className={`font-semibold tabular-nums ${toneClass(
                              valueTone(summary?.total_return_pct ?? null),
                            )}`}
                          >
                            {formatPct(summary?.total_return_pct ?? null)}
                          </span>
                          <button
                            type="button"
                            className="text-xs text-stone-500 underline"
                            onClick={() =>
                              setPeerTickers((prev) => prev.filter((t) => t !== ticker))
                            }
                          >
                            Remove
                          </button>
                        </li>
                      );
                    })}
                    <li>
                      <button
                        type="button"
                        className="text-xs text-stone-500 underline"
                        onClick={() => {
                          setPeerTickers([]);
                          setPeerQuery("");
                        }}
                      >
                        Clear all peers
                      </button>
                    </li>
                  </ul>
                ) : null}
                {peerFrom ? (
                  <p className="mt-1 text-xs text-stone-500">
                    Peer window {formatDate(peerFrom)} → {formatDate(asOf)}
                  </p>
                ) : null}
              </div>

              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">
                  Normalized (100 = period start)
                </p>
                {seriesQuery.isLoading ? (
                  <p className="text-sm text-stone-500">Loading series…</p>
                ) : seriesQuery.data ? (
                  <CompareChart series={seriesQuery.data} />
                ) : (
                  <p className="text-sm text-stone-500">Series unavailable.</p>
                )}
              </div>

              {industryQuery.data && industryQuery.data.peers.length > 0 ? (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-stone-500">
                    Industry peers ({industryQuery.data.industry})
                  </p>
                  <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-sm">
                    {industryQuery.data.peers.map((peer) => (
                      <li
                        key={peer.security_id}
                        className="flex justify-between gap-2 border-b border-stone-100 py-1"
                      >
                        <span className="truncate">{peer.portfolio_name}</span>
                        <span className={`tabular-nums ${toneClass(valueTone(peer.total_return_pct))}`}>
                          {formatPct(peer.total_return_pct)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <p className="text-xs text-stone-500">
                Mcap{" "}
                {selected.mcap == null
                  ? "—"
                  : `${formatNum(selected.mcap)} Cr`}{" "}
                · Portfolio weight {formatPct(selected.position_weight_pct)} · Unrealized{" "}
                {formatPct(selected.unrealized_pnl_pct)} ({formatPnL(selected.unrealized_pnl)}) ·
                qty {selected.quantity}
              </p>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
