"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, type ResearchGoal, type WatchlistSearchHit } from "@/lib/api";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "not yet";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "not yet";
  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function isOpenGoal(goal: ResearchGoal): boolean {
  return goal.status === "accepted" || goal.status === "proposed";
}

export function ResearchHome() {
  const router = useRouter();
  const [firmSearch, setFirmSearch] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(firmSearch), 300);
    return () => window.clearTimeout(timer);
  }, [firmSearch]);

  const statusQuery = useQuery({
    queryKey: ["research-status"],
    queryFn: () => api.getResearchStatus(),
  });
  const goalsQuery = useQuery({
    queryKey: ["research-goals", null],
    queryFn: () => api.listResearchGoals(null),
  });

  const firmHitsQuery = useQuery({
    queryKey: ["research-firm-search", debounced],
    queryFn: () => api.searchWatchlistSecurities(debounced, 20, false),
    enabled: debounced.trim().length >= 2,
  });

  const openGoals = useMemo(
    () => (goalsQuery.data ?? []).filter(isOpenGoal),
    [goalsQuery.data],
  );
  const attention = openGoals.slice(0, 8);
  const continueFirms = useMemo(() => {
    const counts = new Map<string, number>();
    for (const goal of openGoals) {
      counts.set(goal.security_id, (counts.get(goal.security_id) ?? 0) + 1);
    }
    return [...counts.entries()].slice(0, 6);
  }, [openGoals]);

  function openFirm(securityId: string) {
    router.push(`/research/company/${encodeURIComponent(securityId)}`);
  }

  const loadError = statusQuery.isError || goalsQuery.isError;

  return (
    <div className="mx-auto max-w-3xl space-y-10 px-4 py-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <h1 className="font-serif text-3xl text-stone-900 md:text-4xl">Research</h1>
          <p className="max-w-xl text-stone-600">
            Your investment research, organized. Open a company, or add a note.
          </p>
        </div>
        <Link
          href="/research?view=tools"
          className="inline-flex min-h-11 items-center justify-center border border-stone-800 px-4 py-2 text-sm text-stone-900 hover:bg-stone-900 hover:text-white"
        >
          + Add research
        </Link>
      </header>

      <section aria-labelledby="research-search-heading" className="space-y-2">
        <h2 id="research-search-heading" className="sr-only">
          Search a company
        </h2>
        <label className="block text-sm text-stone-700" htmlFor="research-company-search">
          Search a company
          <input
            id="research-company-search"
            type="search"
            className="mt-1 w-full border border-stone-300 bg-transparent px-3 py-3 text-base"
            value={firmSearch}
            onChange={(e) => setFirmSearch(e.target.value)}
            placeholder="Type a name or symbol"
            autoComplete="off"
          />
        </label>
        {debounced.trim().length >= 2 ? (
          <ul className="divide-y divide-stone-100 border border-stone-200">
            {firmHitsQuery.isFetching ? (
              <li className="px-3 py-3 text-sm text-stone-500">Searching…</li>
            ) : firmHitsQuery.isError ? (
              <li className="px-3 py-3 text-sm text-red-800">Search failed. Try again.</li>
            ) : (firmHitsQuery.data ?? []).length === 0 ? (
              <li className="px-3 py-3 text-sm text-stone-500">No matches</li>
            ) : (
              (firmHitsQuery.data ?? []).map((hit: WatchlistSearchHit, index: number) => (
                <li key={`${hit.security_id ?? hit.portfolio_name}-${index}`}>
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-start justify-between gap-3 px-3 py-3 text-left hover:bg-stone-50"
                    disabled={!hit.security_id}
                    onClick={() => {
                      if (hit.security_id) openFirm(hit.security_id);
                    }}
                  >
                    <span>
                      <span className="block text-sm text-stone-900">{hit.portfolio_name}</span>
                      <span className="block text-xs text-stone-500">
                        {[hit.nse_symbol, hit.bse_code, hit.security_id].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-emerald-800">Open</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        ) : null}
      </section>

      <section aria-labelledby="needs-attention-heading" className="space-y-3 border-t border-stone-200 pt-6">
        <h2 id="needs-attention-heading" className="text-lg text-stone-900">
          Needs attention
        </h2>
        {loadError ? (
          <p className="text-sm text-red-800">Could not load research. Refresh the page.</p>
        ) : goalsQuery.isLoading ? (
          <p className="text-sm text-stone-500">Loading…</p>
        ) : attention.length === 0 ? (
          <p className="text-sm text-stone-600">
            Nothing waiting. Your research workspace is ready. Import a thesis or open a company to
            begin.
          </p>
        ) : (
          <ul className="space-y-3">
            {attention.map((goal) => (
              <li
                key={goal.goal_id}
                className="flex flex-col gap-2 border-b border-stone-100 pb-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-stone-900">{goal.title}</p>
                  <p className="text-xs text-stone-500">
                    Open question · {goal.security_id}
                  </p>
                </div>
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center border border-stone-800 px-3 py-2 text-sm"
                  onClick={() => openFirm(goal.security_id)}
                >
                  Continue
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="continue-heading" className="space-y-3 border-t border-stone-200 pt-6">
        <h2 id="continue-heading" className="text-lg text-stone-900">
          Continue researching
        </h2>
        {continueFirms.length === 0 ? (
          <p className="text-sm text-stone-600">No companies with open questions yet.</p>
        ) : (
          <ul className="space-y-3">
            {continueFirms.map(([securityId, count]) => (
              <li
                key={securityId}
                className="flex flex-col gap-2 border-b border-stone-100 pb-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <p className="text-stone-900">
                  {securityId}
                  <span className="block text-xs text-stone-500">
                    {count} open {count === 1 ? "question" : "questions"}
                  </span>
                </p>
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center border border-stone-300 px-3 py-2 text-sm"
                  onClick={() => openFirm(securityId)}
                >
                  Open
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="border-t border-stone-200 pt-4 text-sm text-stone-500">
        Library updated {formatWhen(statusQuery.data?.last_indexed_at)}
        {statusQuery.data ? ` · ${statusQuery.data.document_count} documents` : ""}
        {" · "}
        <Link href="/research?view=tools" className="underline-offset-2 hover:underline">
          Advanced tools
        </Link>
      </footer>
    </div>
  );
}
