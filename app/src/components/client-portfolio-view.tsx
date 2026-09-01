"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type ClientPortfolioDashboard,
  type ClientPortfolioYearlySeries,
  type PortfolioView,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import { DraftTray, holdingsDraftDomain } from "@/components/draft-tray";
import { DailyEditPanel } from "@/components/daily-edit-panel";
import { ViewModeToggle } from "@/components/view-mode-toggle";

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
  const [view, setView] = useState<PortfolioView>("official");

  const dashQuery = useQuery({
    queryKey: ["client-portfolio-dashboard", book, asOf ?? "latest", view],
    queryFn: () => api.getClientPortfolioDashboard(asOf, book, view),
  });

  const draftDomain = holdingsDraftDomain(book);

  const draftQuery = useQuery({
    queryKey: ["change-requests", "my-draft", draftDomain],
    queryFn: () => api.listChangeRequests("draft", draftDomain),
    enabled: view === "mine" && Boolean(dashQuery.data?.approval_workflow),
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
                {data?.approval_workflow
                  ? " Quantity edits use My Working → submit → Samir approves."
                  : null}
              </>
            ) : (
              <>
                Qnty / Index / Date from DailyEditFiles{" "}
                <span className="font-medium">PMS_ClientPortfolio.xlsx</span>. Price, Value,
                Percent, Mcap, %Firm, and Total_Value use the as-of bhav day (Mcap = Excel
                share factor × close).
                {data?.approval_workflow
                  ? " Quantity edits use My Working → submit → Samir approves; Index and Mcap save directly to the shared database."
                  : " Edit holdings in Excel — this page is view-only for positions."}
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {data?.approval_workflow ? (
            <ViewModeToggle view={view} onChange={setView} disabled={dashQuery.isFetching} />
          ) : null}
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

      {book === "client" && data?.approval_workflow ? (
        <DailyEditPanel category="client_portfolio" />
      ) : null}

      {data?.as_of ? (
        <p className="text-sm text-stone-500">
          Marks from bhav{" "}
          <span className="font-medium text-stone-800">{formatDate(data.as_of)}</span>.
          Benchmark yearly tables show Portfolio + BSE SmallCap (Start/End editable for the
          current year).
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

      {data?.approval_workflow && view === "mine" ? (
        <DraftTray draft={draftQuery.data?.[0]} book={book} />
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
          qtyEditable={Boolean(data.approval_workflow) && view === "mine"}
          fieldsEditable={Boolean(data.approval_workflow) && book === "client"}
        />
      ) : null}
      {data?.yearly?.length ? (
        <YearlySection
          series={data.yearly}
          currentYear={Number((asOf ?? data.as_of ?? "").slice(0, 4)) || new Date().getFullYear()}
        />
      ) : null}
    </div>
  );
}

function ModelTable({
  rows,
  total,
  book,
  bankBalance,
  portfolioTotal,
  qtyEditable = false,
  fieldsEditable = false,
}: {
  rows: ClientPortfolioDashboard["holdings"];
  total: number | null | undefined;
  book: "client" | "sca";
  bankBalance?: number | null;
  portfolioTotal?: number | null;
  qtyEditable?: boolean;
  fieldsEditable?: boolean;
}) {
  const sca = book === "sca";
  const queryClient = useQueryClient();
  const [qtyDrafts, setQtyDrafts] = useState<Record<string, string>>({});
  const [indexDrafts, setIndexDrafts] = useState<Record<string, string>>({});

  const saveQty = useMutation({
    mutationFn: ({ symbol, qty }: { symbol: string; qty: number }) =>
      api.patchClientPositionQty(symbol, qty, book),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["change-requests"] });
    },
  });

  const saveFields = useMutation({
    mutationFn: ({
      symbol,
      body,
    }: {
      symbol: string;
      body: { index_label?: string | null; mcap_factor?: number | null };
    }) => api.patchClientPositionFields(symbol, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
    },
  });
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
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {qtyEditable ? (
                    <input
                      type="text"
                      inputMode="numeric"
                      className="w-24 rounded border border-stone-200 px-2 py-0.5 text-right text-sm"
                      value={qtyDrafts[row.symbol] ?? String(row.qty ?? "")}
                      onChange={(e) =>
                        setQtyDrafts((prev) => ({ ...prev, [row.symbol]: e.target.value }))
                      }
                      onBlur={() => {
                        const raw = (qtyDrafts[row.symbol] ?? String(row.qty ?? "")).replace(
                          /,/g,
                          "",
                        );
                        const parsed = Number(raw);
                        if (!Number.isFinite(parsed) || parsed === row.qty) return;
                        saveQty.mutate({ symbol: row.symbol, qty: parsed });
                      }}
                    />
                  ) : (
                    num(row.qty, 0)
                  )}
                  {row.change_status ? (
                    <span className="ml-1 text-[10px] uppercase text-amber-700">
                      {row.change_status}
                    </span>
                  ) : null}
                </td>
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
                    <td className="px-3 py-1.5">
                      {fieldsEditable ? (
                        <input
                          type="text"
                          className="w-28 rounded border border-stone-200 px-2 py-0.5 text-sm"
                          value={indexDrafts[row.symbol] ?? row.index_label ?? ""}
                          onChange={(e) =>
                            setIndexDrafts((prev) => ({
                              ...prev,
                              [row.symbol]: e.target.value,
                            }))
                          }
                          onBlur={() => {
                            const raw = indexDrafts[row.symbol] ?? row.index_label ?? "";
                            const trimmed = raw.trim();
                            if (trimmed === (row.index_label ?? "")) return;
                            saveFields.mutate({
                              symbol: row.symbol,
                              body: { index_label: trimmed || null },
                            });
                          }}
                        />
                      ) : (
                        row.index_label ?? "—"
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {fieldsEditable ? (
                        <input
                          type="text"
                          inputMode="decimal"
                          className="w-24 rounded border border-stone-200 px-2 py-0.5 text-right text-sm"
                          defaultValue={row.mcap != null ? String(row.mcap) : ""}
                          key={`${row.symbol}-${row.mcap ?? "x"}`}
                          onBlur={(e) => {
                            const price = row.price ?? row.close;
                            if (price == null || price === 0) return;
                            const parsed = Number(e.target.value.replace(/,/g, ""));
                            if (!Number.isFinite(parsed)) return;
                            const factor = parsed / price;
                            if (
                              row.mcap_factor != null &&
                              Math.abs(factor - row.mcap_factor) < 1e-6
                            ) {
                              return;
                            }
                            saveFields.mutate({
                              symbol: row.symbol,
                              body: { mcap_factor: factor },
                            });
                          }}
                        />
                      ) : (
                        num(row.mcap)
                      )}
                    </td>
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
      {saveFields.isError ? (
        <p className="text-sm text-red-700">{(saveFields.error as Error).message}</p>
      ) : null}
    </div>
  );
}


function isSmallCap(name: string): boolean {
  const key = name.replace(/\s+/g, "").toUpperCase();
  return key.includes("SMALLCAP") || key === "BSESMALLCAP";
}

function YearlySection({
  series,
  currentYear,
}: {
  series: ClientPortfolioYearlySeries[];
  currentYear: number;
}) {
  const shown = series.filter(
    (block) => block.name === "Portfolio" || isSmallCap(block.name),
  );
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-stone-700">Yearly returns</h3>
      <div className="grid gap-4 xl:grid-cols-2">
        {shown.map((block) => (
          <YearlyTable
            key={block.name}
            block={block}
            editableYear={isSmallCap(block.name) ? currentYear : null}
          />
        ))}
      </div>
    </div>
  );
}

function parseLocalNum(raw: string | undefined, fallback: number | null): number | null {
  if (raw == null) return fallback;
  const n = Number(raw.replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

const SMALLCAP_EDITS_KEY = "pms-bse-smallcap-edits";

type SmallcapYearEdit = { start?: string; end?: string };

function loadSmallcapEdits(): Record<string, SmallcapYearEdit> {
  try {
    const raw = localStorage.getItem(SMALLCAP_EDITS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, SmallcapYearEdit>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveSmallcapYearEdit(year: number, edit: SmallcapYearEdit | null) {
  const all = loadSmallcapEdits();
  if (edit == null || (edit.start == null && edit.end == null)) delete all[String(year)];
  else all[String(year)] = edit;
  localStorage.setItem(SMALLCAP_EDITS_KEY, JSON.stringify(all));
}

function YearlyTable({
  block,
  editableYear,
}: {
  block: ClientPortfolioYearlySeries;
  editableYear: number | null;
}) {
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [ready, setReady] = useState(false);
  const [saveNote, setSaveNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const draftKey = (year: number, field: "start" | "end") => `${year}:${field}`;

  useEffect(() => {
    if (editableYear == null) {
      setReady(true);
      return;
    }
    const stored = loadSmallcapEdits()[String(editableYear)];
    const next: Record<string, string> = {};
    if (stored?.start != null) next[draftKey(editableYear, "start")] = stored.start;
    if (stored?.end != null) next[draftKey(editableYear, "end")] = stored.end;
    setDrafts(next);
    if (stored?.start != null || stored?.end != null) {
      setSaveNote("Using browser-saved values (Excel write was unavailable earlier).");
    }
    setReady(true);
  }, [editableYear]);

  const display = (year: number, field: "start" | "end", value: number | null) => {
    const key = draftKey(year, field);
    if (key in drafts) return drafts[key];
    return value == null || !Number.isFinite(value) ? "" : String(value);
  };
  const valueAt = (year: number, field: "start" | "end", fallback: number | null) =>
    parseLocalNum(drafts[draftKey(year, field)], fallback);

  let firstStart: number | null = null;
  for (const r of block.rows) {
    const s = valueAt(r.year, "start", r.start);
    if (s != null) {
      firstStart = s;
      break;
    }
  }

  const commit = async (
    year: number,
    field: "start" | "end",
    raw: string,
    previous: number | null,
  ) => {
    const parsed = Number(raw.replace(/,/g, ""));
    if (!Number.isFinite(parsed)) {
      setDrafts((d) => {
        const next = { ...d };
        delete next[draftKey(year, field)];
        return next;
      });
      return;
    }
    if (previous != null && parsed === previous && !(draftKey(year, field) in drafts)) return;

    setSaving(true);
    setSaveNote(null);
    try {
      await api.patchBseSmallcapYear({ year, [field]: parsed });
      setDrafts((d) => {
        const next = { ...d };
        delete next[draftKey(year, field)];
        return next;
      });
      const stored = loadSmallcapEdits()[String(year)] ?? {};
      const cleaned = { ...stored };
      delete cleaned[field];
      saveSmallcapYearEdit(year, cleaned.start == null && cleaned.end == null ? null : cleaned);
      setSaveNote("Saved to Excel.");
      void queryClient.invalidateQueries({ queryKey: ["client-portfolio-dashboard"] });
    } catch (err) {
      const text = String(parsed);
      setDrafts((d) => ({ ...d, [draftKey(year, field)]: text }));
      const stored = loadSmallcapEdits()[String(year)] ?? {};
      saveSmallcapYearEdit(year, { ...stored, [field]: text });
      const detail = err instanceof Error ? apiDetail(err) : "Excel save failed";
      setSaveNote(`Could not save to Excel (${detail}). Kept in this browser instead.`);
    } finally {
      setSaving(false);
    }
  };

  if (!ready) return null;

  return (
    <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.06em] text-stone-500">
          <tr>
            <th className="px-3 py-2" colSpan={5}>
              {block.name}
              {editableYear != null ? (
                <span className="ml-2 font-normal normal-case tracking-normal text-stone-500">
                  (edit Start/End for {editableYear} — Excel first, browser backup)
                </span>
              ) : null}
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
          {block.rows.map((row) => {
            const canEdit = editableYear != null && row.year === editableYear;
            const start = canEdit ? valueAt(row.year, "start", row.start) : row.start;
            const end = canEdit ? valueAt(row.year, "end", row.end) : row.end;
            const returnPct =
              canEdit && start != null && end != null && start !== 0
                ? (end / start - 1) * 100
                : row.return_pct;
            const cumPct =
              canEdit && firstStart != null && firstStart !== 0 && end != null
                ? (end / firstStart - 1) * 100
                : row.cum_pct;
            return (
              <tr key={row.year} className="border-t border-stone-100">
                <td className="px-3 py-1.5 tabular-nums">{row.year}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {canEdit ? (
                    <input
                      type="text"
                      inputMode="decimal"
                      aria-label={`${block.name} ${row.year} start`}
                      value={display(row.year, "start", row.start)}
                      disabled={saving}
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [draftKey(row.year, "start")]: e.target.value }))
                      }
                      onBlur={(e) => void commit(row.year, "start", e.target.value, row.start)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") e.currentTarget.blur();
                      }}
                      className="w-28 rounded border border-stone-200 bg-white px-2 py-1 text-right tabular-nums outline-none ring-emerald-600/30 focus:ring-2"
                    />
                  ) : (
                    num(row.start)
                  )}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {canEdit ? (
                    <input
                      type="text"
                      inputMode="decimal"
                      aria-label={`${block.name} ${row.year} end`}
                      value={display(row.year, "end", row.end)}
                      disabled={saving}
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [draftKey(row.year, "end")]: e.target.value }))
                      }
                      onBlur={(e) => void commit(row.year, "end", e.target.value, row.end)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") e.currentTarget.blur();
                      }}
                      className="w-28 rounded border border-stone-200 bg-white px-2 py-1 text-right tabular-nums outline-none ring-emerald-600/30 focus:ring-2"
                    />
                  ) : (
                    num(row.end)
                  )}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">{pct(returnPct)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{pct(cumPct)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {saveNote ? <p className="px-3 py-2 text-sm text-stone-600">{saveNote}</p> : null}
    </div>
  );
}
