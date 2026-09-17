"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  api,
  type ResearchAnalystResult,
  type ResearchGoal,
  type ResearchSearchHit,
} from "@/lib/api";

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: unknown };
      if (typeof parsed.detail === "string") return parsed.detail;
    } catch {
      /* plain */
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Request failed";
}

function agendaItems(response: Record<string, unknown>): Array<{
  title: string;
  rationale?: string;
  priority?: number;
}> {
  const raw = response.research_agenda;
  if (!Array.isArray(raw)) return [];
  const out: Array<{ title: string; rationale?: string; priority?: number }> = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    if (typeof row.title !== "string") continue;
    out.push({
      title: row.title,
      rationale: typeof row.rationale === "string" ? row.rationale : undefined,
      priority: typeof row.priority === "number" ? row.priority : undefined,
    });
  }
  return out;
}

function monitoringItems(response: Record<string, unknown>): Array<{
  item: string;
  cadence?: string;
  why?: string;
}> {
  const raw = response.monitoring_checklist;
  if (!Array.isArray(raw)) return [];
  const out: Array<{ item: string; cadence?: string; why?: string }> = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as Record<string, unknown>;
    if (typeof row.item !== "string") continue;
    out.push({
      item: row.item,
      cadence: typeof row.cadence === "string" ? row.cadence : undefined,
      why: typeof row.why === "string" ? row.why : undefined,
    });
  }
  return out;
}

function scenarioBlock(
  response: Record<string, unknown>,
  key: "bull" | "base" | "bear",
): { summary: string; citations: string[] } {
  const scenarios = response.scenarios;
  if (!scenarios || typeof scenarios !== "object") {
    return { summary: "—", citations: [] };
  }
  const row = (scenarios as Record<string, unknown>)[key];
  if (!row || typeof row !== "object") return { summary: "—", citations: [] };
  const data = row as Record<string, unknown>;
  return {
    summary: typeof data.summary === "string" ? data.summary : "—",
    citations: asStringList(data.citations),
  };
}

function citationLabels(response: Record<string, unknown>): string[] {
  const raw = response.citations;
  if (!Array.isArray(raw)) return [];
  const labels: string[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as Record<string, unknown>;
    const path = typeof row.relative_path === "string" ? row.relative_path : null;
    const page = typeof row.page === "number" ? row.page : null;
    const quote = typeof row.quote_span === "string" ? row.quote_span : null;
    if (path && page != null) {
      labels.push(quote ? `${path}:${page} — ${quote}` : `${path}:${page}`);
    }
  }
  return labels;
}

export function ResearchAnalystView() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const initialSecurity = searchParams.get("security_id")?.trim() ?? "";
  const [searchQ, setSearchQ] = useState(searchParams.get("q")?.trim() ?? "");
  const [securityId, setSecurityId] = useState(initialSecurity);
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

  const acceptedTitles = useMemo(() => {
    const titles = new Set<string>();
    for (const goal of goalsQuery.data ?? []) {
      titles.add(goal.title.trim().toLowerCase());
    }
    return titles;
  }, [goalsQuery.data]);

  const indexMutation = useMutation({
    mutationFn: () => api.indexResearch(),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["research-status"] });
    },
    onError: (err: unknown) => setError(errorMessage(err)),
  });

  const searchMutation = useMutation({
    mutationFn: () => api.searchResearch(searchQ.trim(), securityId || null),
    onSuccess: (result) => {
      setHits(result);
      setError(null);
    },
    onError: (err: unknown) => setError(errorMessage(err)),
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
    onError: (err: unknown) => setError(errorMessage(err)),
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
    onError: (err: unknown) => setError(errorMessage(err)),
  });

  const dismissGoalMutation = useMutation({
    mutationFn: (goalId: number) => api.updateResearchGoal(goalId, { status: "dismissed" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-goals"] });
    },
    onError: (err: unknown) => setError(errorMessage(err)),
  });

  const thesis = useMemo(() => {
    const map = (brief?.response?.thesis_map ?? {}) as Record<string, unknown>;
    return {
      beliefs: asStringList(map.beliefs),
      mustStayTrue: asStringList(map.must_stay_true),
      falsifiers: asStringList(map.falsifiers),
    };
  }, [brief]);

  const agenda = useMemo(() => (brief ? agendaItems(brief.response) : []), [brief]);
  const monitoring = useMemo(
    () => (brief ? monitoringItems(brief.response) : []),
    [brief],
  );
  const citations = useMemo(
    () => (brief ? citationLabels(brief.response) : []),
    [brief],
  );
  const bull = useMemo(
    () => (brief ? scenarioBlock(brief.response, "bull") : null),
    [brief],
  );
  const base = useMemo(
    () => (brief ? scenarioBlock(brief.response, "base") : null),
    [brief],
  );
  const bear = useMemo(
    () => (brief ? scenarioBlock(brief.response, "bear") : null),
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
        <p className="max-w-2xl text-xs text-stone-500">
          When a brief is generated, retrieved text snippets (not whole PDFs) may be sent to xAI.
          Leave XAI_API_KEY unset to keep search local-only.
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
                  {hit.security_id ? (
                    <>
                      {" "}
                      ·{" "}
                      <button
                        type="button"
                        className="underline-offset-2 hover:underline"
                        onClick={() => setSecurityId(hit.security_id!)}
                      >
                        use {hit.security_id}
                      </button>
                    </>
                  ) : null}
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
              {agenda.map((item) => {
                const accepted = acceptedTitles.has(item.title.trim().toLowerCase());
                return (
                  <li
                    key={item.title}
                    className="flex flex-col gap-2 border-b border-stone-100 pb-3 md:flex-row md:items-start md:justify-between"
                  >
                    <div>
                      <p className="text-stone-900">{item.title}</p>
                      {item.rationale ? (
                        <p className="text-sm text-stone-600">{item.rationale}</p>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      className="shrink-0 border border-stone-700 px-3 py-1 text-xs uppercase tracking-wide disabled:opacity-50"
                      disabled={!securityId.trim() || accepted || acceptGoalMutation.isPending}
                      onClick={() => acceptGoalMutation.mutate(item)}
                    >
                      {accepted ? "Accepted" : "Accept goal"}
                    </button>
                  </li>
                );
              })}
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

          {monitoring.length > 0 ? (
            <div>
              <h3 className="text-sm uppercase tracking-wide text-stone-500">
                Monitoring checklist
              </h3>
              <ul className="mt-3 space-y-2">
                {monitoring.map((row) => (
                  <li key={row.item} className="text-sm text-stone-800">
                    <span className="text-stone-900">{row.item}</span>
                    {row.cadence ? (
                      <span className="text-stone-500"> · {row.cadence}</span>
                    ) : null}
                    {row.why ? <p className="text-stone-600">{row.why}</p> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {bull && base && bear ? (
            <div>
              <h3 className="text-sm uppercase tracking-wide text-stone-500">Scenarios</h3>
              <div className="mt-3 grid gap-4 md:grid-cols-3">
                {(
                  [
                    ["Bull", bull],
                    ["Base", base],
                    ["Bear", bear],
                  ] as const
                ).map(([label, block]) => (
                  <div key={label}>
                    <p className="text-sm font-medium text-stone-900">{label}</p>
                    <p className="mt-1 text-sm text-stone-700">{block.summary}</p>
                    {block.citations.length > 0 ? (
                      <p className="mt-1 text-xs text-stone-500">
                        {block.citations.join(" · ")}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {citations.length > 0 ? (
            <div>
              <h3 className="text-sm uppercase tracking-wide text-stone-500">Citations</h3>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-stone-700">
                {citations.map((label) => (
                  <li key={label}>{label}</li>
                ))}
              </ul>
            </div>
          ) : null}
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
