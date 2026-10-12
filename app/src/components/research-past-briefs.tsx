"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function ResearchPastBriefs() {
  const briefsQuery = useQuery({
    queryKey: ["research-briefs"],
    queryFn: () => api.listSavedBriefs(),
  });
  const briefs = briefsQuery.data ?? [];

  return (
    <section aria-labelledby="past-briefs-heading" className="space-y-3 border-t border-stone-200 pt-6">
      <h2 id="past-briefs-heading" className="text-lg text-stone-900">
        Past briefs
      </h2>
      <p className="text-sm text-stone-600">
        Briefs already written. Opening one does not write a new brief.
      </p>
      {briefsQuery.isLoading ? (
        <p className="text-sm text-stone-500">Loading…</p>
      ) : briefsQuery.isError ? (
        <p className="text-sm text-red-800">Could not load past briefs.</p>
      ) : briefs.length === 0 ? (
        <p className="text-sm text-stone-600">No briefs yet. Write one from a company’s notes.</p>
      ) : (
        <ul className="space-y-3">
          {briefs.map((brief) => (
            <li key={brief.cache_id} className="border-b border-stone-100 pb-3">
              <Link
                href={`/research/library?brief=${brief.cache_id}`}
                className="block hover:bg-stone-50"
              >
                <p className="text-stone-900">
                  {brief.company}
                  {brief.created_at ? (
                    <span className="text-sm text-stone-500"> · {formatWhen(brief.created_at)}</span>
                  ) : null}
                </p>
                {brief.summary ? <p className="text-sm text-stone-600">{brief.summary}</p> : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
