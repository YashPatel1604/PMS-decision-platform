"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  api,
  type Watchlist,
  type WatchlistMember,
  type WatchlistSearchHit,
} from "@/lib/api";
import { WatchlistScreener } from "@/components/watchlist-screener";
import { WatchlistAlertsStrip } from "@/components/watchlist-alerts-strip";
import { WatchlistHealthPanel } from "@/components/watchlist-health-panel";

function memberKey(hit: WatchlistSearchHit, index: number): string {
  return hit.security_id ?? hit.yahoo_ticker ?? `${hit.portfolio_name}-${index}`;
}

function researchBadge(status: WatchlistMember["research_status"]): {
  label: string;
  className: string;
} {
  switch (status) {
    case "researched":
      return { label: "Researched", className: "bg-emerald-50 text-emerald-900" };
    case "backlog":
      return { label: "Backlog", className: "bg-amber-50 text-amber-950" };
    default:
      return { label: "Unlinked", className: "bg-stone-100 text-stone-600" };
  }
}

function MemberFixRow({
  member,
  onSaved,
}: {
  member: WatchlistMember;
  onSaved: (msg: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [nse, setNse] = useState(member.nse_symbol ?? "");
  const [bse, setBse] = useState(member.bse_code ?? "");

  const fixMutation = useMutation({
    mutationFn: () =>
      api.updateWatchlistMember(member.watchlist_id, member.member_id, {
        nse_symbol: nse || undefined,
        bse_code: bse || undefined,
      }),
    onSuccess: () => {
      setOpen(false);
      onSaved(`Updated symbols for ${member.display_name}`);
    },
    onError: (err: Error) => onSaved(err.message),
  });

  const resolveMutation = useMutation({
    mutationFn: () => api.resolveWatchlistMember(member.watchlist_id, member.member_id),
    onSuccess: () => onSaved(`Re-resolved ${member.display_name}`),
    onError: (err: Error) => onSaved(err.message),
  });

  const needsAttention =
    member.resolution_status !== "RESOLVED" || member.resolution_stale;

  return (
    <tr className="border-t border-stone-100 hover:bg-stone-50/80">
      <td className="px-4 py-3">
        <p className="font-medium">{member.display_name}</p>
        {member.security_id ? (
          <p className="text-[11px] text-stone-500">{member.security_id}</p>
        ) : (
          <p className="text-[11px] text-amber-800">No security id — re-resolve to enable Research</p>
        )}
        {member.resolution_note ? (
          <p className="text-xs text-stone-500">{member.resolution_note}</p>
        ) : null}
      </td>
      <td className="px-4 py-3 tabular-nums text-stone-600">{member.nse_symbol ?? "—"}</td>
      <td className="px-4 py-3 tabular-nums text-stone-600">{member.bse_code ?? "—"}</td>
      <td className="px-4 py-3 text-stone-600">{member.sector ?? member.industry ?? "—"}</td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-1">
          {(() => {
            const badge = researchBadge(member.research_status ?? "unlinked");
            return (
              <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${badge.className}`}>
                {badge.label}
              </span>
            );
          })()}
          <span
            className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${
              member.resolution_status === "RESOLVED" && !member.resolution_stale
                ? "bg-emerald-50 text-emerald-900"
                : member.resolution_status === "FAILED"
                  ? "bg-red-50 text-red-800"
                  : "bg-amber-50 text-amber-900"
            }`}
          >
            {member.resolution_status}
          </span>
          {member.resolution_stale ? (
            <span
              className="inline-flex rounded-md bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600"
              title="Symbol link is older than 7 days — click Re-resolve"
            >
              Stale link
            </span>
          ) : null}
          {needsAttention ? (
            <span className="text-amber-600" title="Needs symbol fix or re-resolve">
              ⚠
            </span>
          ) : null}
          {member.resolution_source ? (
            <span className="text-[10px] uppercase text-stone-400">{member.resolution_source}</span>
          ) : null}
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex flex-wrap justify-end gap-2">
          {open ? (
            <div className="flex flex-col gap-2 rounded-lg border border-stone-200 bg-stone-50 p-2 text-left">
              <input
                value={nse}
                onChange={(e) => setNse(e.target.value)}
                placeholder="NSE symbol"
                className="w-28 rounded border border-stone-200 px-2 py-1 text-xs"
              />
              <input
                value={bse}
                onChange={(e) => setBse(e.target.value)}
                placeholder="BSE code"
                className="w-28 rounded border border-stone-200 px-2 py-1 text-xs"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => fixMutation.mutate()}
                  disabled={fixMutation.isPending}
                  className="text-xs font-medium text-emerald-800"
                >
                  Save
                </button>
                <button type="button" onClick={() => setOpen(false)} className="text-xs text-stone-500">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              {member.security_id ? (
                <Link
                  href={`/research?security_id=${encodeURIComponent(member.security_id)}`}
                  className="text-xs font-medium text-emerald-800 hover:underline"
                >
                  Research
                </Link>
              ) : null}
              {needsAttention ? (
                <button
                  type="button"
                  onClick={() => setOpen(true)}
                  className="text-xs font-medium text-amber-800 hover:underline"
                >
                  Fix
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => resolveMutation.mutate()}
                disabled={resolveMutation.isPending}
                className="text-xs font-medium text-stone-600 hover:underline"
              >
                Re-resolve
              </button>
              <button
                type="button"
                onClick={() =>
                  api.removeWatchlistMember(member.watchlist_id, member.member_id).then(() =>
                    onSaved("Stock removed"),
                  )
                }
                className="text-xs font-medium text-red-700 hover:underline"
              >
                Remove
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

export function WatchlistsView() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"members" | "screener" | "health">("members");
  const [newListName, setNewListName] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [includeYahoo, setIncludeYahoo] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setIncludeYahoo(false);
  }, [debouncedSearch]);

  const listsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => api.listWatchlists(),
  });

  const activeWatchlist = useMemo(() => {
    const rows = listsQuery.data ?? [];
    if (!rows.length) return null;
    if (activeId != null) {
      return rows.find((r) => r.watchlist_id === activeId) ?? rows[0];
    }
    return rows.find((r) => r.is_default) ?? rows[0];
  }, [listsQuery.data, activeId]);

  const membersQuery = useQuery({
    queryKey: ["watchlist-members", activeWatchlist?.watchlist_id],
    queryFn: () => api.listWatchlistMembers(activeWatchlist!.watchlist_id),
    enabled: activeWatchlist != null && activeTab === "members",
  });

  const searchQuery = useQuery({
    queryKey: ["watchlist-search", debouncedSearch, includeYahoo],
    queryFn: () => api.searchWatchlistSecurities(debouncedSearch, 20, includeYahoo),
    enabled: debouncedSearch.trim().length >= 2,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    await queryClient.invalidateQueries({ queryKey: ["watchlist-members"] });
    await queryClient.invalidateQueries({ queryKey: ["watchlist-screen"] });
    await queryClient.invalidateQueries({ queryKey: ["watchlist-health"] });
  };

  const notify = async (msg: string) => {
    setMessage(msg);
    await invalidate();
  };

  const createMutation = useMutation({
    mutationFn: () => api.createWatchlist({ name: newListName.trim() }),
    onSuccess: async (row) => {
      setNewListName("");
      setActiveId(row.watchlist_id);
      await notify(`Created watchlist "${row.name}"`);
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (row: Watchlist) => api.deleteWatchlist(row.watchlist_id),
    onSuccess: async () => {
      setActiveId(null);
      await notify("Watchlist deleted");
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const addMutation = useMutation({
    mutationFn: (hit: WatchlistSearchHit) =>
      api.addWatchlistMember(activeWatchlist!.watchlist_id, {
        security_id: hit.security_id ?? undefined,
        portfolio_name: hit.security_id ? undefined : hit.portfolio_name,
        nse_symbol: hit.nse_symbol ?? undefined,
        bse_code: hit.bse_code ?? undefined,
        display_name: hit.portfolio_name,
      }),
    onSuccess: async () => {
      setSearch("");
      setResearchFilter("all");
      await notify("Stock added to watchlist");
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        try {
          const parsed = JSON.parse(err.message) as { detail?: unknown };
          if (typeof parsed.detail === "string") {
            setMessage(parsed.detail);
            return;
          }
        } catch {
          /* plain */
        }
        setMessage(err.message);
        return;
      }
      setMessage(err instanceof Error ? err.message : "Add failed");
    },
  });

  const bulkMutation = useMutation({
    mutationFn: () => api.addWatchlistMembersBulk(activeWatchlist!.watchlist_id, pasteText),
    onSuccess: async (result) => {
      setPasteText("");
      setShowPaste(false);
      setResearchFilter("all");
      await notify(
        `Added ${result.added} (${result.pending} pending resolve), skipped ${result.skipped}`,
      );
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        try {
          const parsed = JSON.parse(err.message) as { detail?: unknown };
          if (typeof parsed.detail === "string") {
            setMessage(parsed.detail);
            return;
          }
        } catch {
          /* plain */
        }
        setMessage(err.message);
        return;
      }
      setMessage(err instanceof Error ? err.message : "Bulk add failed");
    },
  });

  const resolveAllMutation = useMutation({
    mutationFn: () => api.resolveWatchlist(activeWatchlist!.watchlist_id),
    onSuccess: async (result) => {
      await notify(
        `Resolution: ${result.resolved} ok, ${result.failed} failed, ${result.skipped} skipped`,
      );
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const refreshMutation = useMutation({
    mutationFn: () => api.refreshWatchlist(activeWatchlist!.watchlist_id),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["watchlist-alerts"] });
      await queryClient.invalidateQueries({ queryKey: ["watchlist-screen"] });
      await queryClient.invalidateQueries({ queryKey: ["watchlist-members"] });
      await queryClient.invalidateQueries({ queryKey: ["watchlist-alerts-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["watchlist-health"] });
      setMessage(
        `Refresh done in ${result.duration_ms}ms · resolved ${result.resolution.resolved}, ` +
          `alerts +${result.alerts.inserted}` +
          (result.fundamentals
            ? `, snapshots ${result.fundamentals.snapshots_written}`
            : ""),
      );
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const setDefaultMutation = useMutation({
    mutationFn: (row: Watchlist) =>
      api.updateWatchlist(row.watchlist_id, { make_default: true }),
    onSuccess: async () => notify("Default watchlist updated"),
    onError: (err: Error) => setMessage(err.message),
  });

  const [researchFilter, setResearchFilter] = useState<"all" | "backlog" | "researched">(
    "all",
  );

  if (listsQuery.isLoading) {
    return <p className="text-stone-600">Loading watchlists…</p>;
  }

  const lists = listsQuery.data ?? [];
  const allMembers = membersQuery.data ?? [];
  const researchedCount = allMembers.filter((m) => m.research_status === "researched").length;
  const backlogCount = allMembers.filter((m) => m.research_status === "backlog").length;
  const unlinkedCount = allMembers.filter((m) => (m.research_status ?? "unlinked") === "unlinked").length;
  const members = [...allMembers]
    .filter((m) => {
      if (researchFilter === "all") return true;
      return (m.research_status ?? "unlinked") === researchFilter;
    })
    .sort((a, b) => {
      const rank = (s: string | undefined) =>
        s === "backlog" ? 0 : s === "unlinked" ? 1 : 2;
      const d = rank(a.research_status) - rank(b.research_status);
      if (d !== 0) return d;
      return a.display_name.localeCompare(b.display_name);
    });
  const hits = searchQuery.data ?? [];
  const unresolvedCount = allMembers.filter(
    (m) => m.resolution_status !== "RESOLVED" || m.resolution_stale,
  ).length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Watchlists</h2>
        <p className="mt-2 max-w-2xl text-stone-600">
          Manage multiple lists in-app. Symbols resolve via security master → BSE → Yahoo.
          Research badges show which names already have a brief/thesis/docs vs still need deep
          research (backlog).
        </p>
      </div>

      {message ? (
        <p className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm text-stone-700">
          {message}
        </p>
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <aside className="w-full max-w-xs shrink-0 space-y-3 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-stone-500">
            Your lists
          </p>
          <div className="space-y-1">
            {lists.map((row) => (
              <button
                key={row.watchlist_id}
                type="button"
                onClick={() => setActiveId(row.watchlist_id)}
                className={[
                  "flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition",
                  activeWatchlist?.watchlist_id === row.watchlist_id
                    ? "bg-emerald-50 font-medium text-emerald-900"
                    : "text-stone-700 hover:bg-stone-50",
                ].join(" ")}
              >
                <span>{row.name}</span>
                <span className="text-xs tabular-nums text-stone-500">
                  {row.member_count}
                  {row.is_default ? " · default" : ""}
                </span>
              </button>
            ))}
          </div>
          <form
            className="flex gap-2 pt-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!newListName.trim()) return;
              createMutation.mutate();
            }}
          >
            <input
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              placeholder="New watchlist name"
              className="min-w-0 flex-1 rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none ring-emerald-600/30 focus:ring-2"
            />
            <button
              type="submit"
              disabled={createMutation.isPending || !newListName.trim()}
              className="rounded-lg bg-emerald-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Add
            </button>
          </form>
        </aside>

        <div className="min-w-0 flex-1 space-y-4">
          {!activeWatchlist ? (
            <div className="rounded-xl border border-stone-200 bg-white p-8 text-center text-stone-600">
              Create your first watchlist to start tracking stocks.
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="text-lg font-semibold">{activeWatchlist.name}</h3>
                <div className="inline-flex rounded-lg border border-stone-200 p-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setActiveTab("members")}
                    className={`rounded-md px-3 py-1.5 font-medium ${
                      activeTab === "members"
                        ? "bg-emerald-800 text-white"
                        : "text-stone-600 hover:bg-stone-50"
                    }`}
                  >
                    Members
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab("screener")}
                    className={`rounded-md px-3 py-1.5 font-medium ${
                      activeTab === "screener"
                        ? "bg-emerald-800 text-white"
                        : "text-stone-600 hover:bg-stone-50"
                    }`}
                  >
                    Screener
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab("health")}
                    className={`rounded-md px-3 py-1.5 font-medium ${
                      activeTab === "health"
                        ? "bg-emerald-800 text-white"
                        : "text-stone-600 hover:bg-stone-50"
                    }`}
                  >
                    Health
                  </button>
                </div>
                {activeTab === "members" && unresolvedCount > 0 ? (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                    {unresolvedCount} need attention
                  </span>
                ) : null}
                {activeTab === "members" ? (
                  <div className="inline-flex items-center gap-1 rounded-lg border border-stone-200 p-0.5 text-xs">
                    <button
                      type="button"
                      onClick={() => setResearchFilter("all")}
                      className={`rounded-md px-2 py-1 font-medium ${
                        researchFilter === "all" ? "bg-stone-800 text-white" : "text-stone-600"
                      }`}
                    >
                      All {allMembers.length}
                    </button>
                    <button
                      type="button"
                      onClick={() => setResearchFilter("backlog")}
                      className={`rounded-md px-2 py-1 font-medium ${
                        researchFilter === "backlog" ? "bg-amber-800 text-white" : "text-stone-600"
                      }`}
                    >
                      Backlog {backlogCount}
                    </button>
                    <button
                      type="button"
                      onClick={() => setResearchFilter("researched")}
                      className={`rounded-md px-2 py-1 font-medium ${
                        researchFilter === "researched"
                          ? "bg-emerald-800 text-white"
                          : "text-stone-600"
                      }`}
                    >
                      Researched {researchedCount}
                    </button>
                  </div>
                ) : null}
                {activeTab === "members" && unlinkedCount > 0 ? (
                  <span className="text-xs text-stone-500">{unlinkedCount} unlinked</span>
                ) : null}
                <button
                  type="button"
                  onClick={() => refreshMutation.mutate()}
                  disabled={refreshMutation.isPending}
                  className="rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-900 hover:bg-emerald-100"
                >
                  {refreshMutation.isPending ? "Refreshing…" : "Refresh data"}
                </button>
                {activeTab === "members" ? (
                  <>
                <button
                  type="button"
                  onClick={async () => {
                    const blob = await api.exportWatchlistJson(activeWatchlist.watchlist_id);
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${activeWatchlist.name.replace(/\s+/g, "_")}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-600 hover:bg-stone-50"
                >
                  Export JSON
                </button>
                <button
                  type="button"
                  onClick={() => resolveAllMutation.mutate()}
                  disabled={resolveAllMutation.isPending}
                  className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-600 hover:bg-stone-50"
                >
                  {resolveAllMutation.isPending ? "Resolving…" : "Re-resolve stale"}
                </button>
                {!activeWatchlist.is_default ? (
                  <button
                    type="button"
                    onClick={() => setDefaultMutation.mutate(activeWatchlist)}
                    className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-600 hover:bg-stone-50"
                  >
                    Set as default
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete watchlist "${activeWatchlist.name}" and all its stocks?`,
                      )
                    ) {
                      deleteMutation.mutate(activeWatchlist);
                    }
                  }}
                  className="rounded-md border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                >
                  Delete list
                </button>
                  </>
                ) : null}
              </div>

              <WatchlistAlertsStrip watchlistId={activeWatchlist.watchlist_id} />

              {activeTab === "screener" ? (
                <WatchlistScreener watchlistId={activeWatchlist.watchlist_id} />
              ) : activeTab === "health" ? (
                <WatchlistHealthPanel watchlistId={activeWatchlist.watchlist_id} />
              ) : (
              <>
              <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
                <label className="text-sm font-medium text-stone-700">Add stock</label>
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search security master (min 2 chars)"
                  className="mt-2 w-full rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none ring-emerald-600/30 focus:ring-2"
                />
                {debouncedSearch.trim().length >= 2 ? (
                  <ul className="mt-2 divide-y divide-stone-100 rounded-lg border border-stone-100">
                    {searchQuery.isFetching ? (
                      <li className="px-3 py-2 text-sm text-stone-500">Searching…</li>
                    ) : hits.length === 0 ? (
                      <li className="px-3 py-2 text-sm text-stone-500">
                        No master matches.
                        {!includeYahoo ? (
                          <button
                            type="button"
                            onClick={() => setIncludeYahoo(true)}
                            className="ml-2 text-emerald-800 underline"
                          >
                            Search Yahoo
                          </button>
                        ) : null}
                      </li>
                    ) : (
                      hits.map((hit, index) => (
                        <li
                          key={memberKey(hit, index)}
                          className="flex items-center justify-between gap-3 px-3 py-2"
                        >
                          <div>
                            <p className="font-medium text-stone-900">{hit.portfolio_name}</p>
                            <p className="text-xs text-stone-500">
                              {[hit.source, hit.nse_symbol, hit.bse_code, hit.sector]
                                .filter(Boolean)
                                .join(" · ")}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => addMutation.mutate(hit)}
                            disabled={addMutation.isPending}
                            className="rounded-md bg-emerald-800 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
                          >
                            Add
                          </button>
                        </li>
                      ))
                    )}
                  </ul>
                ) : null}
                <button
                  type="button"
                  onClick={() => setShowPaste((open) => !open)}
                  className="mt-3 text-xs font-medium text-stone-600 underline"
                >
                  {showPaste ? "Hide paste" : "Paste names"}
                </button>
                {showPaste ? (
                  <div className="mt-2 space-y-2">
                    <textarea
                      value={pasteText}
                      onChange={(e) => setPasteText(e.target.value)}
                      rows={5}
                      placeholder={"One name or NSE symbol per line\nCaplin Point\nHERITGFOOD"}
                      className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none ring-emerald-600/30 focus:ring-2"
                    />
                    <button
                      type="button"
                      onClick={() => bulkMutation.mutate()}
                      disabled={bulkMutation.isPending || pasteText.trim().length === 0}
                      className="rounded-md bg-emerald-800 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
                    >
                      {bulkMutation.isPending ? "Adding…" : "Add pasted names"}
                    </button>
                    <p className="text-xs text-stone-500">
                      Master hits resolve immediately. Unknown names stay pending until
                      Re-resolve stale.
                    </p>
                  </div>
                ) : null}
              </div>

              <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
                <table className="min-w-full text-sm">
                  <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.08em] text-stone-500">
                    <tr>
                      <th className="px-4 py-3">Company</th>
                      <th className="px-4 py-3">NSE</th>
                      <th className="px-4 py-3">BSE</th>
                      <th className="px-4 py-3">Sector</th>
                      <th className="px-4 py-3">Research / resolve</th>
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {members.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-8 text-center text-stone-500">
                          No stocks yet. Search above to add one.
                        </td>
                      </tr>
                    ) : (
                      members.map((member) => (
                        <MemberFixRow
                          key={member.member_id}
                          member={member}
                          onSaved={notify}
                        />
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
