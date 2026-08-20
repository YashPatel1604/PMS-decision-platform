"use client";

import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, type BlockDeal, type TodayBlockDeals } from "@/lib/api";
import { formatDate, formatInr, formatPrice } from "@/lib/format";

type DealKind = "block" | "bulk";

const KIND_COPY: Record<
  DealKind,
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
  block: {
    title: "Block deals",
    loading: "Loading block deals…",
    errorTitle: "Could not load block deals.",
    description:
      "Official BSE disclosed block deals by session date. Same client buying and selling the same security on the same day is flagged as arbitrage.",
    sourceNote:
      "Green days include our firms. Orange days have market deals only. Grey has none. Source: BSE Bulk / Block Deals (Block Deal type).",
    emptyDay: "No block deals reported for",
    hasDealsTitle: (d) => `Block deals on ${d}`,
    noDealsTitle: "No block deals this day",
  },
  bulk: {
    title: "Bulk deals",
    loading: "Loading bulk deals…",
    errorTitle: "Could not load bulk deals.",
    description:
      "Official BSE disclosed bulk deals by session date. Same client buying and selling the same security on the same day is flagged as arbitrage.",
    sourceNote:
      "Green days include our firms. Orange days have market deals only. Grey has none. Source: BSE Bulk / Block Deals (Bulk Deal type).",
    emptyDay: "No bulk deals reported for",
    hasDealsTitle: (d) => `Bulk deals on ${d}`,
    noDealsTitle: "No bulk deals this day",
  },
};

function formatQty(value: number | string): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(n);
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

function fetchDeals(
  kind: DealKind,
  date: string | null,
  month: string | null,
): Promise<TodayBlockDeals> {
  return kind === "bulk"
    ? api.getTodayBulkDeals(date, month)
    : api.getTodayBlockDeals(date, month);
}

export function BlockDealsView() {
  return <DisclosedDealsView kind="block" />;
}

export function BulkDealsView() {
  return <DisclosedDealsView kind="bulk" />;
}

function DisclosedDealsView({ kind }: { kind: DealKind }) {
  const copy = KIND_COPY[kind];
  const [hideArb, setHideArb] = useState(true);
  const [query, setQuery] = useState("");
  const [minMarketCapCr, setMinMarketCapCr] = useState("2000");
  const [maxMarketCapCr, setMaxMarketCapCr] = useState("");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [viewMonth, setViewMonth] = useState<string | null>(null);

  const dealsQuery = useQuery({
    queryKey: [`${kind}-deals`, selectedDate ?? "latest", viewMonth ?? "auto"],
    queryFn: () => fetchDeals(kind, selectedDate, viewMonth),
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (!dealsQuery.data?.as_of_date || dealsQuery.isFetching) return;
    if (!viewMonth) {
      setViewMonth(toMonthKey(dealsQuery.data.as_of_date));
    }
    if (!selectedDate) {
      const month = viewMonth ?? toMonthKey(dealsQuery.data.as_of_date);
      const inMonth = (dealsQuery.data.available_dates ?? []).filter((d) =>
        d.startsWith(month),
      );
      setSelectedDate(inMonth[0] ?? dealsQuery.data.as_of_date);
    }
  }, [dealsQuery.data, dealsQuery.isFetching, selectedDate, viewMonth]);

  const availableSet = useMemo(
    () => new Set(dealsQuery.data?.available_dates ?? []),
    [dealsQuery.data?.available_dates],
  );
  const portfolioSet = useMemo(
    () => new Set(dealsQuery.data?.portfolio_dates ?? []),
    [dealsQuery.data?.portfolio_dates],
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
    const deals = dealsQuery.data?.deals ?? [];
    const q = query.trim().toLowerCase();
    return deals.filter((deal) => {
      if (hideArb && deal.is_arbitrage) return false;
      const cap =
        deal.market_cap_cr == null || !Number.isFinite(Number(deal.market_cap_cr))
          ? null
          : Number(deal.market_cap_cr);
      if (minCap != null && (cap == null || cap < minCap)) return false;
      if (maxCap != null && (cap == null || cap > maxCap)) return false;
      if (!q) return true;
      const haystack = [
        deal.bse_code,
        deal.scrip_name,
        deal.client_name,
        deal.portfolio_name ?? "",
        deal.deal_type,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [dealsQuery.data?.deals, hideArb, query, minCap, maxCap]);

  if (dealsQuery.isLoading && !dealsQuery.data) {
    return <p className="text-stone-600">{copy.loading}</p>;
  }

  if (dealsQuery.isError && !dealsQuery.data) {
    return (
      <div className="space-y-4">
        <Header
          title={copy.title}
          description={copy.description}
          onRefresh={() => void dealsQuery.refetch()}
          refreshing={dealsQuery.isFetching}
        />
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-900">
          <p className="font-semibold">{copy.errorTitle}</p>
          <p className="mt-2 text-sm">
            {(dealsQuery.error as Error)?.message ||
              "The exchange feed may be unavailable. Try Refresh in a moment."}
          </p>
        </div>
      </div>
    );
  }

  const data = dealsQuery.data;
  if (!data) return null;

  const calendarMonth = viewMonth ?? toMonthKey(data.as_of_date);
  const activeDate = selectedDate ?? data.as_of_date;
  const arbHidden = hideArb ? data.deals.filter((d) => d.is_arbitrage).length : 0;

  return (
    <div className="space-y-6">
      <Header
        title={copy.title}
        description={copy.description}
        onRefresh={() => void dealsQuery.refetch()}
        refreshing={dealsQuery.isFetching}
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <DealCalendar
          monthKey={calendarMonth}
          selectedDate={activeDate}
          availableDates={availableSet}
          portfolioDates={portfolioSet}
          loading={dealsQuery.isFetching}
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
              <input
                type="checkbox"
                className="size-4 rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
                checked={hideArb}
                onChange={(e) => setHideArb(e.target.checked)}
              />
              Hide arbitrage
            </label>
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
              Showing {filtered.length} of {data.deal_count}
              {arbHidden > 0 ? ` · ${arbHidden} arb deals hidden` : ""}
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
            placeholder="Filter by scrip, client, code…"
            className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 shadow-sm outline-none ring-emerald-600/30 placeholder:text-stone-400 focus:ring-2 sm:max-w-xs"
          />
          <p className="text-xs text-stone-500">{copy.sourceNote}</p>
        </div>
      </div>

      {data.deal_count === 0 ? (
        <div className="rounded-xl border border-stone-200 bg-white p-8 text-center text-stone-600">
          {copy.emptyDay} {formatDate(data.as_of_date)}.
          {availableSet.size > 0
            ? " Pick a highlighted session date on the calendar."
            : ""}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-stone-200 bg-white p-8 text-center text-stone-600">
          No deals match the current filters.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.08em] text-stone-500">
              <tr>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Scrip</th>
                <th className="px-4 py-3 text-right">Mcap (₹ Cr)</th>
                <th className="px-4 py-3">Client</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-right">Value</th>
                <th className="px-4 py-3">Portfolio</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((deal, index) => (
                <DealRow
                  key={`${deal.deal_date}-${deal.bse_code}-${deal.client_name}-${deal.deal_type}-${index}`}
                  deal={deal}
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
  portfolioDates,
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
  portfolioDates: Set<string>;
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
          const ours = portfolioDates.has(cell.iso);
          const selected = cell.iso === selectedDate;
          return (
            <button
              key={cell.iso}
              type="button"
              disabled={!hasDeals}
              onClick={() => onSelectDate(cell.iso!)}
              title={
                ours
                  ? `${hasDealsTitle(formatDate(cell.iso))} (our firms)`
                  : hasDeals
                    ? `${hasDealsTitle(formatDate(cell.iso))} (market only)`
                    : noDealsTitle
              }
              className={[
                "aspect-square rounded-md text-sm tabular-nums transition",
                selected && ours
                  ? "bg-emerald-800 font-semibold text-white"
                  : selected && hasDeals
                    ? "bg-orange-700 font-semibold text-white"
                    : ours
                      ? "bg-emerald-50 font-medium text-emerald-900 hover:bg-emerald-100"
                      : hasDeals
                        ? "bg-orange-50 font-medium text-orange-900 hover:bg-orange-100"
                        : "cursor-not-allowed text-stone-300",
              ].join(" ")}
            >
              {cell.day}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-stone-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-emerald-600" />
          Our firms
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-orange-400" />
          Market only
        </span>
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

function formatMarketCapCr(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: n >= 100 ? 0 : 2,
  }).format(n);
}

function DealRow({ deal }: { deal: BlockDeal }) {
  const buy = deal.deal_type === "BUY";
  return (
    <tr className="border-t border-stone-100 hover:bg-stone-50/80">
      <td className="px-4 py-3 tabular-nums text-stone-600">
        {deal.deal_date ? formatDate(deal.deal_date) : "—"}
      </td>
      <td className="px-4 py-3">
        <span
          className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
            buy ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"
          }`}
        >
          {deal.deal_type}
        </span>
        {deal.is_arbitrage ? (
          <span className="ml-2 inline-flex items-center rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
            Arb
          </span>
        ) : null}
      </td>
      <td className="px-4 py-3">
        <p className="font-medium text-stone-900">{deal.scrip_name || "—"}</p>
        <p className="text-xs text-stone-500">{deal.bse_code}</p>
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-stone-700">
        {formatMarketCapCr(deal.market_cap_cr)}
      </td>
      <td className="max-w-[18rem] px-4 py-3 text-stone-700">{deal.client_name || "—"}</td>
      <td className="px-4 py-3 text-right tabular-nums">{formatQty(deal.quantity)}</td>
      <td className="px-4 py-3 text-right tabular-nums">{formatPrice(Number(deal.price))}</td>
      <td className="px-4 py-3 text-right tabular-nums">{formatInr(Number(deal.value))}</td>
      <td className="px-4 py-3">
        {deal.in_portfolio ? (
          <span
            className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${
              deal.is_open ? "bg-emerald-50 text-emerald-900" : "bg-stone-100 text-stone-700"
            }`}
          >
            {deal.portfolio_name}
            {deal.is_open ? " · open" : ""}
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        )}
      </td>
    </tr>
  );
}
