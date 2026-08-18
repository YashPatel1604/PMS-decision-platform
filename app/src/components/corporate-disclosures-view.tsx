"use client";

import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, type CorporateDisclosure, type TodayCorporateDisclosures } from "@/lib/api";
import { formatDate, formatInr, formatPct } from "@/lib/format";

type DisclosureKind = "sast" | "insider";

const KIND_COPY: Record<
  DisclosureKind,
  {
    title: string;
    loading: string;
    errorTitle: string;
    description: string;
    sourceNote: string;
    emptyDay: string;
    hasDealsTitle: (dateLabel: string) => string;
    noDealsTitle: string;
  }
> = {
  sast: {
    title: "SAST · System driven",
    loading: "Loading SAST disclosures…",
    errorTitle: "Could not load SAST disclosures.",
    description:
      "BSE Regulation 29 system-driven disclosures (acquirer/seller holdings changes from depositories).",
    sourceNote:
      "Days without disclosures are greyed out. Source: BSE corporates/regulation_29. Default min mcap ₹2,000 Cr.",
    emptyDay: "No SAST disclosures reported for",
    hasDealsTitle: (d) => `SAST disclosures on ${d}`,
    noDealsTitle: "No SAST disclosures this day",
  },
  insider: {
    title: "Insider trading 2015",
    loading: "Loading insider disclosures…",
    errorTitle: "Could not load insider disclosures.",
    description:
      "BSE Insider Trading Regulations 2015 disclosures submitted by the company (Reg 7(2)).",
    sourceNote:
      "Days without filings are grey. History is stored after the first day-by-day BSE search (BSE returns at most 25 rows per query). Default min mcap ₹2,000 Cr.",
    emptyDay: "No insider disclosures reported for",
    hasDealsTitle: (d) => `Insider disclosures on ${d}`,
    noDealsTitle: "No insider disclosures this day",
  },
};

function formatQty(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(n);
}

function formatMarketCapCr(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: n >= 100 ? 0 : 2,
  }).format(n);
}

function formatPctValue(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return formatPct(n);
}

function toMonthKey(isoDate: string): string {
  return isoDate.slice(0, 7);
}

function shiftMonth(monthKey: string, delta: number): string {
  const [y, m] = monthKey.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

function daysInMonth(monthKey: string): number {
  const [y, m] = monthKey.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

function weekdayMondayFirst(monthKey: string, day: number): number {
  const [y, m] = monthKey.split("-").map(Number);
  const sunFirst = new Date(Date.UTC(y, m - 1, day)).getUTCDay();
  return (sunFirst + 6) % 7;
}

function monthLabel(monthKey: string): string {
  const [y, m] = monthKey.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-IN", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function fetchDisclosures(
  kind: DisclosureKind,
  date: string | null,
  month: string | null,
): Promise<TodayCorporateDisclosures> {
  return kind === "insider"
    ? api.getTodayInsiderTrading(date, month)
    : api.getTodaySastDisclosures(date, month);
}

export function SastDisclosuresView() {
  return <CorporateDisclosuresView kind="sast" />;
}

export function InsiderTradingView() {
  return <CorporateDisclosuresView kind="insider" />;
}

function CorporateDisclosuresView({ kind }: { kind: DisclosureKind }) {
  const copy = KIND_COPY[kind];
  const [query, setQuery] = useState("");
  const [minMarketCapCr, setMinMarketCapCr] = useState("2000");
  const [maxMarketCapCr, setMaxMarketCapCr] = useState("");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [viewMonth, setViewMonth] = useState<string | null>(null);

  const disclosuresQuery = useQuery({
    queryKey: [`${kind}-disclosures`, selectedDate ?? "latest", viewMonth ?? "auto"],
    queryFn: () => fetchDisclosures(kind, selectedDate, viewMonth),
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (!disclosuresQuery.data?.as_of_date || disclosuresQuery.isFetching) return;
    if (!viewMonth) {
      setViewMonth(toMonthKey(disclosuresQuery.data.as_of_date));
    }
    if (!selectedDate) {
      const month = viewMonth ?? toMonthKey(disclosuresQuery.data.as_of_date);
      const inMonth = (disclosuresQuery.data.available_dates ?? []).filter((d) =>
        d.startsWith(month),
      );
      setSelectedDate(inMonth[0] ?? disclosuresQuery.data.as_of_date);
    }
  }, [disclosuresQuery.data, disclosuresQuery.isFetching, selectedDate, viewMonth]);

  const availableSet = useMemo(
    () => new Set(disclosuresQuery.data?.available_dates ?? []),
    [disclosuresQuery.data?.available_dates],
  );

  const minCap = useMemo(() => {
    const n = Number(minMarketCapCr);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [minMarketCapCr]);

  const maxCap = useMemo(() => {
    const n = Number(maxMarketCapCr);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [maxMarketCapCr]);

  const filtered = useMemo(() => {
    const rows = disclosuresQuery.data?.rows ?? [];
    const q = query.trim().toLowerCase();
    return rows.filter((row) => {
      const cap =
        row.market_cap_cr == null || !Number.isFinite(Number(row.market_cap_cr))
          ? null
          : Number(row.market_cap_cr);
      if (minCap != null && (cap == null || cap < minCap)) return false;
      if (maxCap != null && (cap == null || cap > maxCap)) return false;
      if (!q) return true;
      const haystack = [
        row.bse_code,
        row.company_name,
        row.person_name,
        row.category,
        row.transaction_type,
        row.portfolio_name ?? "",
        row.regulation,
        row.mode,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [disclosuresQuery.data?.rows, query, minCap, maxCap]);

  if (disclosuresQuery.isLoading && !disclosuresQuery.data) {
    return <p className="text-stone-600">{copy.loading}</p>;
  }

  if (disclosuresQuery.isError && !disclosuresQuery.data) {
    return (
      <div className="space-y-4">
        <Header
          title={copy.title}
          description={copy.description}
          onRefresh={() => void disclosuresQuery.refetch()}
          refreshing={disclosuresQuery.isFetching}
        />
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-900">
          <p className="font-semibold">{copy.errorTitle}</p>
          <p className="mt-2 text-sm">
            {(disclosuresQuery.error as Error)?.message ||
              "The exchange feed may be unavailable. Try Refresh in a moment."}
          </p>
        </div>
      </div>
    );
  }

  const data = disclosuresQuery.data;
  if (!data) return null;

  const calendarMonth = viewMonth ?? toMonthKey(data.as_of_date);
  const activeDate = selectedDate ?? data.as_of_date;

  return (
    <div className="space-y-6">
      <Header
        title={copy.title}
        description={copy.description}
        onRefresh={() => void disclosuresQuery.refetch()}
        refreshing={disclosuresQuery.isFetching}
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <DealCalendar
          monthKey={calendarMonth}
          selectedDate={activeDate}
          availableDates={availableSet}
          loading={disclosuresQuery.isFetching}
          hasDealsTitle={copy.hasDealsTitle}
          noDealsTitle={copy.noDealsTitle}
          onPrevMonth={() => {
            setSelectedDate(null);
            setViewMonth(shiftMonth(calendarMonth, -1));
          }}
          onNextMonth={() => {
            setSelectedDate(null);
            setViewMonth(shiftMonth(calendarMonth, 1));
          }}
          onSelectDate={(iso) => {
            setSelectedDate(iso);
            setViewMonth(toMonthKey(iso));
          }}
        />

        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-stone-700">
              <span className="font-medium text-stone-600">Min mcap</span>
              <input
                type="number"
                min={0}
                step={100}
                value={minMarketCapCr}
                onChange={(e) => setMinMarketCapCr(e.target.value)}
                className="w-24 rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm tabular-nums shadow-sm outline-none ring-emerald-600/30 focus:ring-2"
              />
              <span className="text-stone-500">₹ Cr</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-stone-700">
              <span className="font-medium text-stone-600">Max mcap</span>
              <input
                type="number"
                min={0}
                step={100}
                value={maxMarketCapCr}
                onChange={(e) => setMaxMarketCapCr(e.target.value)}
                placeholder="Any"
                className="w-24 rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm tabular-nums shadow-sm outline-none ring-emerald-600/30 placeholder:text-stone-400 focus:ring-2"
              />
              <span className="text-stone-500">₹ Cr</span>
            </label>
            <p className="text-sm text-stone-500">
              Showing {filtered.length} of {data.row_count}
              {minCap != null ? ` · mcap ≥ ${minCap.toLocaleString("en-IN")} Cr` : ""}
              {maxCap != null ? ` · mcap ≤ ${maxCap.toLocaleString("en-IN")} Cr` : ""}
              {" · "}
              {formatDate(data.as_of_date)}
            </p>
          </div>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by company, person, code…"
            className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 shadow-sm outline-none ring-emerald-600/30 placeholder:text-stone-400 focus:ring-2 sm:max-w-xs"
          />
          <p className="text-xs text-stone-500">{copy.sourceNote}</p>
        </div>
      </div>

      {data.row_count === 0 ? (
        <div className="rounded-xl border border-stone-200 bg-white p-8 text-center text-stone-600">
          {copy.emptyDay} {formatDate(data.as_of_date)}.
          {availableSet.size > 0
            ? " Pick a highlighted session date on the calendar."
            : ""}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-stone-200 bg-white p-8 text-center text-stone-600">
          No disclosures match the current filters.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.08em] text-stone-500">
              <tr>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3 text-right">Mcap (₹ Cr)</th>
                <th className="px-4 py-3">Person</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Txn</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Value</th>
                <th className="px-4 py-3 text-right">% pre→post</th>
                <th className="px-4 py-3">Portfolio</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, index) => (
                <DisclosureRow
                  key={`${row.disclosure_date}-${row.bse_code}-${row.person_name}-${row.transaction_type}-${index}`}
                  row={row}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DealCalendar({
  monthKey,
  selectedDate,
  availableDates,
  loading,
  hasDealsTitle,
  noDealsTitle,
  onPrevMonth,
  onNextMonth,
  onSelectDate,
}: {
  monthKey: string;
  selectedDate: string;
  availableDates: Set<string>;
  loading: boolean;
  hasDealsTitle: (dateLabel: string) => string;
  noDealsTitle: string;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onSelectDate: (iso: string) => void;
}) {
  const totalDays = daysInMonth(monthKey);
  const lead = weekdayMondayFirst(monthKey, 1);
  const cells: Array<{ day: number | null; iso: string | null }> = [];
  for (let i = 0; i < lead; i += 1) cells.push({ day: null, iso: null });
  for (let day = 1; day <= totalDays; day += 1) {
    const iso = `${monthKey}-${String(day).padStart(2, "0")}`;
    cells.push({ day, iso });
  }
  while (cells.length % 7 !== 0) cells.push({ day: null, iso: null });

  return (
    <div className="w-full max-w-sm shrink-0 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onPrevMonth}
          className="rounded-md px-2 py-1 text-sm text-stone-600 hover:bg-stone-100"
          aria-label="Previous month"
        >
          ‹
        </button>
        <div className="text-center">
          <p className="text-sm font-semibold text-stone-900">{monthLabel(monthKey)}</p>
          {loading ? <p className="text-[11px] text-stone-400">Updating…</p> : null}
        </div>
        <button
          type="button"
          onClick={onNextMonth}
          className="rounded-md px-2 py-1 text-sm text-stone-600 hover:bg-stone-100"
          aria-label="Next month"
        >
          ›
        </button>
      </div>
      <div className="mb-1 grid grid-cols-7 gap-1 text-center text-[11px] font-medium uppercase tracking-wide text-stone-400">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, idx) => {
          if (cell.day == null || cell.iso == null) {
            return <div key={`pad-${idx}`} className="aspect-square" />;
          }
          const hasDeals = availableDates.has(cell.iso);
          const selected = cell.iso === selectedDate;
          return (
            <button
              key={cell.iso}
              type="button"
              disabled={!hasDeals}
              onClick={() => onSelectDate(cell.iso!)}
              title={
                hasDeals ? hasDealsTitle(formatDate(cell.iso)) : noDealsTitle
              }
              className={[
                "aspect-square rounded-md text-sm tabular-nums transition",
                selected
                  ? "bg-emerald-800 font-semibold text-white"
                  : hasDeals
                    ? "bg-emerald-50 font-medium text-emerald-900 hover:bg-emerald-100"
                    : "cursor-not-allowed text-stone-300",
              ].join(" ")}
            >
              {cell.day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Header({
  title,
  description,
  onRefresh,
  refreshing,
}: {
  title: string;
  description: string;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
        <p className="mt-2 text-stone-600">{description}</p>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        className="rounded-lg bg-emerald-800 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-900 disabled:opacity-60"
      >
        {refreshing ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );
}

function DisclosureRow({ row }: { row: CorporateDisclosure }) {
  return (
    <tr className="border-t border-stone-100 hover:bg-stone-50/80">
      <td className="px-4 py-3 tabular-nums text-stone-600">
        {row.disclosure_date ? formatDate(row.disclosure_date) : "—"}
      </td>
      <td className="px-4 py-3">
        <p className="font-medium text-stone-900">{row.company_name || "—"}</p>
        <p className="text-xs text-stone-500">
          {row.bse_code || "—"}
          {row.regulation ? ` · ${row.regulation}` : ""}
        </p>
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-stone-700">
        {formatMarketCapCr(row.market_cap_cr)}
      </td>
      <td className="max-w-[16rem] px-4 py-3 text-stone-700">{row.person_name || "—"}</td>
      <td className="px-4 py-3 text-stone-700">{row.category || "—"}</td>
      <td className="px-4 py-3">
        <p className="text-stone-800">{row.transaction_type || "—"}</p>
        {row.mode ? <p className="text-xs text-stone-500">{row.mode}</p> : null}
      </td>
      <td className="px-4 py-3 text-right tabular-nums">{formatQty(row.quantity)}</td>
      <td className="px-4 py-3 text-right tabular-nums">
        {row.value != null ? formatInr(Number(row.value)) : "—"}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-stone-700">
        {formatPctValue(row.pct_pre)} → {formatPctValue(row.pct_post)}
      </td>
      <td className="px-4 py-3">
        {row.in_portfolio ? (
          <span
            className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${
              row.is_open ? "bg-emerald-50 text-emerald-900" : "bg-stone-100 text-stone-700"
            }`}
          >
            {row.portfolio_name}
            {row.is_open ? " · open" : ""}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        )}
      </td>
    </tr>
  );
}
