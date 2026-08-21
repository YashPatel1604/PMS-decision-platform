"use client";

import { formatDate } from "@/lib/format";

/** Shared month calendar for BSE deal / disclosure day pickers. */

export function toMonthKey(isoDate: string): string {
  return isoDate.slice(0, 7);
}

export function shiftMonth(monthKey: string, delta: number): string {
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

export function DealCalendar({
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

export function DealRefreshHeader({
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
