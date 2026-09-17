"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type ResearchAnalystResult,
  type ResearchGoal,
  type ResearchSearchHit,
} from "@/lib/api";

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function agendaItems(response: Record<string, unknown>): Array<{
  title: string;
  rationale?: string;
  priority?: number;
}> {
  const raw = response.research_agenda;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      if (typeof row.title !== "string") return null;
      return {
        title: row.title,
        rationale: typeof row.rationale === "string" ? row.rationale : undefined,
        priority: typeof row.priority === "number" ? row.priority : undefined,
      };
    })
    .filter((item): item is { title: string; rationale?: string; priority?: number } => item !== null);
}

export function ResearchAnalystView() {
  const queryClient = useQueryClient();
  const [searchQ, setSearchQ] = useState("");
  const [securityId, setSecurityId] = useState("");
  const [hits, setHits] = useState<ResearchSearchHit[]>([]);
  const [brief, setBrief] = useState<ResearchAnalystResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: ["research-status"],
    queryFn: () => api.getResearchStatus(),
  });

  const goalsQuery = useQuery({
    queryKey: ["research-goals", securityId || null],
    queryFn: () => api.listResearchGoals(securityId || null),
  });

  const indexMutation = useMutation({
    mutationFn: () => api.indexResearch(),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["research-status"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const searchMutation = useMutation({
    mutationFn: () => api.searchResearch(searchQ.trim(), securityId || null),
    onSuccess: (result) => {
      setHits(result);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const briefMutation = useMutation({
    mutationFn: () =>
      api.generateResearchBrief({
        security_id: securityId.trim() || null,
        query_name: securityId.trim() ? null : searchQ.trim() || null,
        force_refresh: false,
      }),
    onSuccess: (result) => {
      setBrief(result);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const acceptGoalMutation = useMutation({
    mutationFn: (item: { title: string; rationale?: string; priority?: number }) => {
      if (!securityId.trim()) throw new Error("Set security id before accepting goals");
      return api.createResearchGoal({
        security_id: securityId.trim(),
        title: item.title,
        rationale: item.rationale ?? null,
        priority: item.priority ?? 0,
        source_cache_id: brief?.cache_id ?? null,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-goals"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const dismissGoalMutation = useMutation({
    mutationFn: (goalId: number) => api.updateResearchGoal(goalId, { status: "dismissed" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-goals"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const thesis = useMemo(() => {
    const map = (brief?.response?.thesis_map ?? {}) as Record<string, unknown>;
    return {
      beliefs: asStringList(map.beliefs),
      mustStayTrue: asStringList(map.must_stay_true),
      falsifiers: asStringList(map.falsifiers),
    };
  }, [brief]);

  const agenda = useMemo(
    () => (brief ? agendaItems(brief.response) : []),
    [brief],
  );

  return (
    <div className="mx-auto max-w-5xl space-y-10 px-4 py-8">
      <header className="space-y-3">
        <p className="text-sm uppercase tracking-[0.2em] text-stone-500">Research</p>
        <h1 className="font-serif text-3xl text-stone-900 md:text-4xl">Analyst assistant</h1>
        <p className="max-w-2xl text-stone-600">
          Index local Research notes, retrieve evidence, then generate a citation-backed research
          agenda. Portfolio math stays in deterministic code — Grok only helps set future research
          goals.
        </p>
      </header>

      <section className="space-y-3 border-t border-stone-200 pt-6">
        <h2 className="text-lg text-stone-900">Index</h2>
        <p className="text-sm text-stone-600">
          Documents: {statusQuery.data?.document_count ?? "—"} · Pages:{" "}
          {statusQuery.data?.page_count ?? "—"} · Last indexed:{" "}
          {statusQuery.data?.last_indexed_at ?? "never"}
        </p>
        <button
          type="button"
          className="border border-stone-800 px-4 py-2 text-sm text-stone-900 hover:bg-stone-900 hover:text-white disabled:opacity-50"
          onClick={() => indexMutation.mutate()}
          disabled={indexMutation.isPending}
        >
          {indexMutation.isPending ? "Indexing…" : "Re-index Research"}
        </button>
      </section>

      <section className="space-y-4 border-t border-stone-200 pt-6">
        <h2 className="text-lg text-stone-900">Search and brief</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-sm text-stone-700">
            Security id
            <input
              className="mt-1 w-full border border-stone-300 bg-transparent px-3 py-2"
              value={securityId}
              onChange={(e) => setSecurityId(e.target.value)}
              placeholder="e.g. SEC001"
            />
          </label>
          <label className="block text-sm text-stone-700">
            Search query / name
            <input
              className="mt-1 w-full border border-stone-300 bg-transparent px-3 py-2"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              placeholder="promoter pledge"
            />
          </label>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className="border border-stone-800 px-4 py-2 text-sm hover:bg-stone-900 hover:text-white disabled:opacity-50"
            onClick={() => searchMutation.mutate()}
            disabled={searchMutation.isPending || !searchQ.trim()}
          >
            {searchMutation.isPending ? "Searching…" : "Search index"}
          </button>
          <button
            type="button"
            className="border border-stone-800 px-4 py-2 text-sm hover:bg-stone-900 hover:text-white disabled:opacity-50"
            onClick={() => briefMutation.mutate()}
            disabled={briefMutation.isPending || (!securityId.trim() && !searchQ.trim())}
          >
            {briefMutation.isPending ? "Generating…" : "Generate research brief"}
          </button>
        </div>
        {error ? <p className="text-sm text-red-800">{error}</p> : null}
        {brief ? (
          <p className="text-xs text-stone-500">
            cache_hit={String(brief.cache_hit)} · called_llm={String(brief.called_llm)} · tokens_in=
            {brief.token_in ?? "—"} · tokens_out={brief.token_out ?? "—"}
          </p>
        ) : null}
      </section>

      {hits.length > 0 ? (
        <section className="space-y-3 border-t border-stone-200 pt-6">
          <h2 className="text-lg text-stone-900">Search hits</h2>
          <ul className="space-y-4">
            {hits.map((hit) => (
              <li key={hit.page_id} className="border-l-2 border-stone-300 pl-3">
                <p className="text-sm text-stone-900">
                  {hit.relative_path}:{hit.page_number}
                </p>
                <p className="text-sm text-stone-600">{hit.snippet}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {brief ? (
        <section className="space-y-6 border-t border-stone-200 pt-6">
          <h2 className="text-lg text-stone-900">Brief</h2>
          <div className="grid gap-6 md:grid-cols-3">
            <div>
              <h3 className="text-sm uppercase tracking-wide text-stone-500">Beliefs</h3>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-stone-800">
                {thesis.beliefs.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm uppercase tracking-wide text-stone-500">Must stay true</h3>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-stone-800">
                {thesis.mustStayTrue.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm uppercase tracking-wide text-stone-500">Falsifiers</h3>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-stone-800">
                {thesis.falsifiers.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>

          <div>
            <h3 className="text-sm uppercase tracking-wide text-stone-500">Research agenda</h3>
            <ul className="mt-3 space-y-3">
              {agenda.map((item) => (
                <li key={item.title} className="flex flex-col gap-2 border-b border-stone-100 pb-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-stone-900">{item.title}</p>
                    {item.rationale ? (
                      <p className="text-sm text-stone-600">{item.rationale}</p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className="shrink-0 border border-stone-700 px-3 py-1 text-xs uppercase tracking-wide disabled:opacity-50"
                    disabled={!securityId.trim() || acceptGoalMutation.isPending}
                    onClick={() => acceptGoalMutation.mutate(item)}
                  >
                    Accept goal
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-sm uppercase tracking-wide text-stone-500">Evidence gaps</h3>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-stone-800">
              {asStringList(brief.response.evidence_gaps).map((item) => (
                <li key={item}>{item}</li>
              ))}
              {asStringList(brief.response.insufficient_evidence).map((item) => (
                <li key={`insuf-${item}`}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      <section className="space-y-3 border-t border-stone-200 pt-6">
        <h2 className="text-lg text-stone-900">Accepted goals</h2>
        {(goalsQuery.data ?? []).length === 0 ? (
          <p className="text-sm text-stone-600">No open research goals yet.</p>
        ) : (
          <ul className="space-y-3">
            {(goalsQuery.data as ResearchGoal[]).map((goal) => (
              <li
                key={goal.goal_id}
                className="flex flex-col gap-2 border-b border-stone-100 pb-3 md:flex-row md:items-start md:justify-between"
              >
                <div>
                  <p className="text-stone-900">{goal.title}</p>
                  <p className="text-xs text-stone-500">
                    {goal.security_id} · priority {goal.priority} · {goal.status}
                  </p>
                  {goal.rationale ? (
                    <p className="text-sm text-stone-600">{goal.rationale}</p>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="shrink-0 border border-stone-400 px-3 py-1 text-xs uppercase tracking-wide text-stone-700 disabled:opacity-50"
                  disabled={dismissGoalMutation.isPending}
                  onClick={() => dismissGoalMutation.mutate(goal.goal_id)}
                >
                  Dismiss
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
