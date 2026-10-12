"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ResearchPastBriefs } from "@/components/research-past-briefs";
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
  const [chooseError, setChooseError] = useState<string | null>(null);
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
    queryFn: () => api.searchWatchlistSecurities(debounced, 20, true),
    enabled: debounced.trim().length >= 2,
  });

  const firmsQuery = useQuery({
    queryKey: ["research-firms"],
    queryFn: () => api.listResearchFirms(),
  });
  const companyName = useMemo(() => {
    const names = new Map<string, string>();
    for (const firm of firmsQuery.data ?? []) names.set(firm.security_id, firm.display_name);
    return (securityId: string) => names.get(securityId) || "Unnamed company";
  }, [firmsQuery.data]);
  const openGoals = useMemo(
    () => (goalsQuery.data ?? []).filter(isOpenGoal),
    [goalsQuery.data],
  );
  const byCompany = useMemo(() => {
    const groups = new Map<string, ResearchGoal[]>();
    for (const goal of openGoals) {
      const list = groups.get(goal.security_id) ?? [];
      list.push(goal);
      groups.set(goal.security_id, list);
    }
    return [...groups.entries()].slice(0, 8);
  }, [openGoals]);

  function openFirm(securityId: string) {
    router.push(`/research/company/${encodeURIComponent(securityId)}`);
  }

  async function chooseHit(hit: WatchlistSearchHit) {
    setChooseError(null);
    try {
      if (hit.security_id) {
        openFirm(hit.security_id);
        return;
      }
      const created = await api.ensureResearchCompany({
        name: hit.portfolio_name,
        nse_symbol: hit.nse_symbol,
        bse_code: hit.bse_code,
      });
      openFirm(created.security_id);
    } catch (err) {
      setChooseError(err instanceof Error ? err.message : "Could not add that company");
    }
  }

  async function chooseTypedName() {
    const name = debounced.trim();
    if (name.length < 2) return;
    await chooseHit({
      source: "typed",
      security_id: null,
      portfolio_name: name,
      nse_symbol: null,
      bse_code: null,
      isin: null,
      sector: null,
      industry: null,
    });
  }

  const loadError = statusQuery.isError || goalsQuery.isError;

  return (
    <div className="mx-auto max-w-3xl space-y-10 px-4 py-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <h1 className="font-serif text-3xl text-stone-900 md:text-4xl">Research</h1>
          <p className="max-w-xl text-stone-600">
            Pick a company. Each company page holds only that company’s thesis, files, and questions.
          </p>
        </div>
        <Link
          href="/research/library"
          className="inline-flex min-h-11 items-center justify-center border border-stone-800 px-4 py-2 text-sm text-stone-900 hover:bg-stone-900 hover:text-white"
        >
          Add a file
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
              <li>
                <button
                  type="button"
                  className="flex min-h-11 w-full items-center justify-between px-3 py-3 text-left text-sm hover:bg-stone-50"
                  onClick={() => void chooseTypedName()}
                >
                  <span>Research {debounced.trim()}</span>
                  <span className="text-xs text-emerald-800">Add</span>
                </button>
              </li>
            ) : (
              (firmHitsQuery.data ?? []).map((hit: WatchlistSearchHit, index: number) => (
                <li key={`${hit.security_id ?? hit.portfolio_name}-${index}`}>
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-start justify-between gap-3 px-3 py-3 text-left hover:bg-stone-50"
                    onClick={() => void chooseHit(hit)}
                  >
                    <span>
                      <span className="block text-sm text-stone-900">{hit.portfolio_name}</span>
                      <span className="block text-xs text-stone-500">
                        {[hit.nse_symbol, hit.bse_code].filter(Boolean).join(" · ") || "Open this company"}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-emerald-800">
                      {hit.security_id ? "Open" : "Add"}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        ) : null}
        {chooseError ? <p className="text-sm text-red-800">{chooseError}</p> : null}
      </section>

      <section aria-labelledby="companies-heading" className="space-y-3 border-t border-stone-200 pt-6">
        <h2 id="companies-heading" className="text-lg text-stone-900">
          Companies with open questions
        </h2>
        <p className="text-sm text-stone-600">
          These are questions already saved for a company. Opening one shows only that company.
        </p>
        {loadError ? (
          <p className="text-sm text-red-800">Could not load research. Refresh the page.</p>
        ) : goalsQuery.isLoading ? (
          <p className="text-sm text-stone-500">Loading…</p>
        ) : byCompany.length === 0 ? (
          <p className="text-sm text-stone-600">
            No open questions yet. Search for a company above, or add a file to the library.
          </p>
        ) : (
          <ul className="space-y-4">
            {byCompany.map(([securityId, goals]) => (
              <li
                key={securityId}
                className="flex flex-col gap-2 border-b border-stone-100 pb-3 sm:flex-row sm:items-start sm:justify-between"
              >
                <div>
                  <p className="text-stone-900">{companyName(securityId)}</p>
                  <ul className="mt-1 space-y-1">
                    {goals.slice(0, 3).map((goal) => (
                      <li key={goal.goal_id} className="text-sm text-stone-600">
                        {goal.title}
                      </li>
                    ))}
                  </ul>
                </div>
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center border border-stone-800 px-3 py-2 text-sm"
                  onClick={() => openFirm(securityId)}
                >
                  Open company
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ResearchPastBriefs />

      <footer className="border-t border-stone-200 pt-4 text-sm text-stone-500">
        Library updated {formatWhen(statusQuery.data?.last_indexed_at)}
        {statusQuery.data ? ` · ${statusQuery.data.document_count} documents` : ""}
        {" · "}
        <Link href="/research/library" className="underline-offset-2 hover:underline">
          File library
        </Link>
      </footer>
    </div>
  );
}
