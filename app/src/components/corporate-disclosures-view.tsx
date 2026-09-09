"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, type CorporateDisclosure, type TodayCorporateDisclosures } from "@/lib/api";
import { formatDate, formatInr, formatPct } from "@/lib/format";
import { DealCalendar, DealRefreshHeader, shiftMonth, toMonthKey } from "@/components/deal-calendar";

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
      "Green days include our firms. Orange days have other market filings only. Grey has none. Source: BSE corporates/regulation_29. Table is paged at 25 rows.",
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
      "Green = our firms. Orange = other filings. Grey = none. BSE has no market pagination (25-row cap); capped days are completed by per-scrip fetch of all active equities. Table is paged at 25 rows.",
    emptyDay: "No insider disclosures reported for",
    hasDealsTitle: (d) => `Insider disclosures on ${d}`,
    noDealsTitle: "No insider disclosures this day",
  },
};

const PAGE_SIZE = 25;

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
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

function formatPctValue(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return formatPct(n);
}

function txnLabel(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  return text || "(blank)";
}






function fetchDisclosures(
  kind: DisclosureKind,
  date: string | null,
  month: string | null,
  refreshFromBse = false,
): Promise<TodayCorporateDisclosures> {
  return kind === "insider"
    ? api.getTodayInsiderTrading(date, month, refreshFromBse)
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
  const [hideArb, setHideArb] = useState(true);
  const [txnFilter, setTxnFilter] = useState<string[] | null>(null);
  const [page, setPage] = useState(1);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [viewMonth, setViewMonth] = useState<string | null>(null);
  const refreshFromBse = useRef(false);

  const disclosuresQuery = useQuery({
    queryKey: [
      `${kind}-disclosures`,
      selectedDate ?? "latest",
      viewMonth ?? "auto",
      kind,
    ],
    queryFn: () => fetchDisclosures(kind, selectedDate, viewMonth, refreshFromBse.current),
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });

  const handleRefresh = async () => {
    refreshFromBse.current = kind === "insider";
    try {
      await disclosuresQuery.refetch();
    } finally {
      refreshFromBse.current = false;
    }
  };

  useEffect(() => {
    if (!disclosuresQuery.data?.as_of_date || disclosuresQuery.isFetching) return;
    const dataMonth = toMonthKey(disclosuresQuery.data.as_of_date);
    const month = viewMonth ?? dataMonth;
    if (!viewMonth) {
      setViewMonth(dataMonth);
    }
    const inMonth = (disclosuresQuery.data.available_dates ?? []).filter((d) =>
      d.startsWith(month),
    );
    if (!selectedDate || !selectedDate.startsWith(month)) {
      setSelectedDate(inMonth[0] ?? null);
    }
  }, [disclosuresQuery.data, disclosuresQuery.isFetching, selectedDate, viewMonth]);

  const availableSet = useMemo(() => {
    const month = viewMonth;
    const dates = disclosuresQuery.data?.available_dates ?? [];
    if (!month) return new Set(dates);
    return new Set(dates.filter((d) => d.startsWith(month)));
  }, [disclosuresQuery.data?.available_dates, viewMonth]);
  const portfolioSet = useMemo(() => {
    const month = viewMonth;
    const dates = disclosuresQuery.data?.portfolio_dates ?? [];
    if (!month) return new Set(dates);
    return new Set(dates.filter((d) => d.startsWith(month)));
  }, [disclosuresQuery.data?.portfolio_dates, viewMonth]);

  const minCap = useMemo(() => {
    const n = Number(minMarketCapCr);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [minMarketCapCr]);

  const maxCap = useMemo(() => {
    const n = Number(maxMarketCapCr);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [maxMarketCapCr]);

  const txnOptions = useMemo(() => {
    const names = new Set<string>();
    for (const row of disclosuresQuery.data?.rows ?? []) {
      names.add(txnLabel(row.transaction_type));
    }
    return [...names].sort((a, b) => a.localeCompare(b, "en"));
  }, [disclosuresQuery.data?.rows]);

  useEffect(() => {
    setTxnFilter((current) => {
      if (current === null) return null;
      const allowed = new Set(txnOptions);
      const next = current.filter((name) => allowed.has(name));
      if (next.length === 0 || next.length === txnOptions.length) return null;
      return next;
    });
  }, [txnOptions]);

  const filtered = useMemo(() => {
    const rows = disclosuresQuery.data?.rows ?? [];
    const q = query.trim().toLowerCase();
    const txnAllowed = txnFilter === null ? null : new Set(txnFilter);
    return rows.filter((row) => {
      if (kind === "insider" && hideArb && row.is_arbitrage) return false;
      if (txnAllowed && !txnAllowed.has(txnLabel(row.transaction_type))) return false;
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
  }, [disclosuresQuery.data?.rows, query, minCap, maxCap, hideArb, kind, txnFilter]);

  useEffect(() => {
    setPage(1);
  }, [selectedDate, query, minCap, maxCap, hideArb, kind, txnFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  if (disclosuresQuery.isLoading && !disclosuresQuery.data) {
    return <p className="text-stone-600">{copy.loading}</p>;
  }

  if (disclosuresQuery.isError && !disclosuresQuery.data) {
    return (
      <div className="space-y-4">
        <DealRefreshHeader
          title={copy.title}
          description={copy.description}
          onRefresh={() => void handleRefresh()}
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
      <DealRefreshHeader
        title={copy.title}
        description={copy.description}
        onRefresh={() => void handleRefresh()}
        refreshing={disclosuresQuery.isFetching}
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <DealCalendar
          monthKey={calendarMonth}
          selectedDate={activeDate}
          availableDates={availableSet}
          portfolioDates={portfolioSet}
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
            {kind === "insider" ? (
              <label className="flex cursor-pointer items-center gap-2 text-sm text-stone-700">
                <input
                  type="checkbox"
                  checked={hideArb}
                  onChange={(e) => setHideArb(e.target.checked)}
                  className="rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
                />
                <span>Hide arbitrage</span>
              </label>
            ) : null}
            <p className="text-sm text-stone-500">
              Showing {filtered.length} of {data.row_count}
              {filtered.length > PAGE_SIZE
                ? ` · page ${safePage}/${pageCount}`
                : ""}
              {minCap != null ? ` · mcap ≥ ${minCap.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr` : ""}
              {maxCap != null ? ` · mcap ≤ ${maxCap.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr` : ""}
              {txnFilter != null ? ` · ${txnFilter.length} txn type${txnFilter.length === 1 ? "" : "s"}` : ""}
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
        <div className="space-y-3">
          <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.08em] text-stone-500">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Company</th>
                  <th className="px-4 py-3 text-right">Mcap (₹ Cr)</th>
                  <th className="px-4 py-3">Person</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">
                    <TxnTypeFilter
                      options={txnOptions}
                      selected={txnFilter}
                      onChange={setTxnFilter}
                    />
                  </th>
                  <th className="px-4 py-3 text-right">Qty</th>
                  <th className="px-4 py-3 text-right">Value</th>
                  <th className="px-4 py-3 text-right">% pre→post</th>
                  <th className="px-4 py-3">Portfolio</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row, index) => (
                  <DisclosureRow
                    key={`${row.disclosure_date}-${row.bse_code}-${row.person_name}-${row.transaction_type}-${index}`}
                    row={row}
                  />
                ))}
              </tbody>
            </table>
          </div>
          {pageCount > 1 ? (
            <div className="flex items-center justify-end gap-3 text-sm text-stone-600">
              <button
                type="button"
                disabled={safePage <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded-lg border border-stone-200 bg-white px-3 py-1.5 disabled:opacity-40"
              >
                Previous
              </button>
              <span>
                Page {safePage} of {pageCount}
              </span>
              <button
                type="button"
                disabled={safePage >= pageCount}
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                className="rounded-lg border border-stone-200 bg-white px-3 py-1.5 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function TxnTypeFilter({
  options,
  selected,
  onChange,
}: {
  options: string[];
  selected: string[] | null;
  onChange: (next: string[] | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const enabled = selected === null ? options : selected;
  const enabledSet = useMemo(() => new Set(enabled), [enabled]);
  const narrowed = selected !== null;

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle(name: string) {
    const next = new Set(enabledSet);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    if (next.size === 0 || next.size === options.length) onChange(null);
    else onChange([...next]);
  }

  return (
    <div ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="true"
        className={`inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-left text-xs font-semibold uppercase tracking-[0.08em] transition hover:bg-stone-200/70 ${
          narrowed || open ? "text-emerald-800" : "text-stone-500"
        }`}
      >
        Txn
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
          className={`h-3 w-3 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 10.94l3.71-3.71a.75.75 0 1 1 1.06 1.06l-4.24 4.24a.75.75 0 0 1-1.06 0L5.21 8.29a.75.75 0 0 1 .02-1.08Z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open ? (
        <div
          role="group"
          aria-label="Filter by transaction type"
          className="absolute left-0 top-full z-30 mt-1 max-h-64 min-w-[16rem] overflow-y-auto rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
        >
          <label className="flex cursor-pointer items-center gap-2 border-b border-stone-100 px-3 py-2 text-xs font-medium text-stone-700 hover:bg-stone-50">
            <input
              type="checkbox"
              checked={!narrowed}
              onChange={() => onChange(null)}
              className="rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
            />
            All types
          </label>
          {options.length === 0 ? (
            <p className="px-3 py-2 text-xs text-stone-500">No types on this day</p>
          ) : (
            options.map((name) => (
              <label
                key={name}
                className="flex cursor-pointer items-start gap-2 px-3 py-1.5 text-xs font-normal normal-case tracking-normal text-stone-700 hover:bg-stone-50"
              >
                <input
                  type="checkbox"
                  checked={enabledSet.has(name)}
                  onChange={() => toggle(name)}
                  className="mt-0.5 rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
                />
                <span className="leading-snug">{name}</span>
              </label>
            ))
          )}
        </div>
      ) : null}
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
        ) : row.is_arbitrage ? (
          <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900">
            Arbitrage
          </span>
        ) : (
          <span className="text-stone-400">—</span>
        )}
      </td>
    </tr>
  );
}
