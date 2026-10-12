"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";

const PRESETS = [
  "What changed in the notes we have?",
  "What would challenge this thesis?",
  "What do the latest results say?",
  "Which questions are still open?",
] as const;

type Panel = "overview" | "thesis" | "documents" | "questions";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "unknown date";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "unknown date";
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function reviewLabel(decision: string): string {
  if (decision === "unchanged") return "no thesis change";
  if (decision === "investigate") return "needs investigation";
  return decision;
}

function errorText(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) {
    return "AI is unavailable. Your saved thesis and documents are still here.";
  }
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong.";
}

export function ResearchCompanyView({ securityId }: { securityId: string }) {
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<Panel>("overview");
  const [question, setQuestion] = useState("");
  const [thesisPaste, setThesisPaste] = useState("");
  const [monitorPaste, setMonitorPaste] = useState("");
  const [reviewNote, setReviewNote] = useState("");

  const overviewQuery = useQuery({
    queryKey: ["research-company", securityId],
    queryFn: () => api.getResearchCompany(securityId),
  });
  const goalsQuery = useQuery({
    queryKey: ["research-goals", securityId],
    queryFn: () => api.listResearchGoals(securityId),
    enabled: panel === "questions",
  });

  const askMutation = useMutation({
    mutationFn: (text: string) => api.askResearch({ question: text, security_id: securityId }),
  });
  const reviewMutation = useMutation({
    mutationFn: (decision: "unchanged" | "investigate") =>
      api.recordResearchReview(securityId, {
        decision,
        note: reviewNote.trim() || undefined,
      }),
    onSuccess: () => {
      setReviewNote("");
      void queryClient.invalidateQueries({ queryKey: ["research-company", securityId] });
    },
  });
  const approveMutation = useMutation({
    mutationFn: (thesisId: number) => api.approveInvestmentThesis(thesisId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-company", securityId] });
    },
  });
  const thesisMutation = useMutation({
    mutationFn: () =>
      api.createInvestmentThesis({
        security_id: securityId,
        thesis_summary: thesisPaste.trim(),
        key_monitoring_variables: monitorPaste.trim() || null,
        status: "active",
      }),
    onSuccess: () => {
      setThesisPaste("");
      setMonitorPaste("");
      void queryClient.invalidateQueries({ queryKey: ["research-company", securityId] });
    },
  });

  const company = overviewQuery.data;
  const answer = askMutation.data?.response;
  const answerText = typeof answer?.answer === "string" ? answer.answer : "";
  const uncertainty = Array.isArray(answer?.insufficient_evidence)
    ? answer.insufficient_evidence.filter((item): item is string => typeof item === "string")
    : [];
  const citations = Array.isArray(answer?.citations) ? answer.citations : [];

  function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    askMutation.mutate(trimmed);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-8">
      <header className="space-y-2">
        <Link href="/research" className="text-sm text-stone-600 underline-offset-2 hover:underline">
          ← Research
        </Link>
        {overviewQuery.isLoading ? (
          <p className="text-sm text-stone-500">Loading company…</p>
        ) : overviewQuery.isError ? (
          <p className="text-sm text-red-800">This company could not be loaded.</p>
        ) : company ? (
          <>
            <h1 className="font-serif text-3xl text-stone-900">{company.name}</h1>
            <p className="text-sm text-stone-600">
              This page is only for {company.name}
              {company.nse_symbol || company.bse_code
                ? ` (${[company.nse_symbol, company.bse_code].filter(Boolean).join(" · ")})`
                : ""}
              . {company.relationship}.
              {company.last_review
                ? ` Last reviewed ${formatWhen(company.last_review.created_at)} (${reviewLabel(company.last_review.decision)}).`
                : " Not yet reviewed."}
            </p>
          </>
        ) : null}
      </header>

      <nav aria-label="Company research" className="flex flex-wrap gap-2">
        {(
          [
            ["overview", "Overview"],
            ["thesis", "Thesis"],
            ["documents", "Documents"],
            ["questions", "Questions"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`min-h-11 border px-3 py-2 text-sm ${
              panel === id ? "border-stone-800 bg-stone-900 text-white" : "border-stone-300 text-stone-800"
            }`}
            aria-current={panel === id ? "page" : undefined}
            onClick={() => setPanel(id)}
          >
            {label}
          </button>
        ))}
        <Link
          href={`/research?view=tools&security_id=${encodeURIComponent(securityId)}`}
          className="inline-flex min-h-11 items-center border border-stone-300 px-3 py-2 text-sm text-stone-700"
        >
          Search this company's files
        </Link>
      </nav>

      {panel === "overview" && company ? (
        <div className="space-y-8">
          <section aria-labelledby="case-heading" className="space-y-2">
            <h2 id="case-heading" className="text-lg text-stone-900">
              Our investment case
            </h2>
            {company.thesis.approval === "none" ? (
              <p className="text-sm text-stone-600">
                No saved thesis yet. Paste one under Thesis. Saving it does not mark it approved.
              </p>
            ) : (
              <>
                <p className="text-xs text-stone-500">
                  {company.thesis.approval === "approved"
                    ? `Approved thesis${company.thesis.version != null ? `, version ${company.thesis.version}` : ""}.`
                    : `Previously saved thesis. Approval is not confirmed.${company.thesis.version != null ? ` Version ${company.thesis.version}.` : ""}`}
                </p>
                <p className="text-stone-800">{company.thesis.summary || "No summary was saved."}</p>
                {company.thesis.assumptions.length > 0 ? (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-stone-800">
                    {company.thesis.assumptions.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
                {company.thesis.pending_thesis_id != null ? (
                  <p className="text-sm text-stone-600">
                    A newer saved version is waiting. It is not the investment case until you approve it.
                  </p>
                ) : null}
              </>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="min-h-11 border border-stone-800 px-3 py-2 text-sm"
                onClick={() => setPanel("thesis")}
              >
                {company.thesis.approval === "none" ? "Add thesis" : "View full thesis"}
              </button>
              {company.thesis.approval === "unconfirmed" && company.thesis.thesis_id != null ? (
                <button
                  type="button"
                  className="min-h-11 border border-stone-800 px-3 py-2 text-sm disabled:opacity-50"
                  disabled={approveMutation.isPending}
                  onClick={() => approveMutation.mutate(company.thesis.thesis_id as number)}
                >
                  Approve thesis
                </button>
              ) : null}
              {company.thesis.pending_thesis_id != null ? (
                <button
                  type="button"
                  className="min-h-11 border border-stone-300 px-3 py-2 text-sm disabled:opacity-50"
                  disabled={approveMutation.isPending}
                  onClick={() => approveMutation.mutate(company.thesis.pending_thesis_id as number)}
                >
                  Approve newer version
                </button>
              ) : null}
            </div>
            {approveMutation.isError ? (
              <p className="text-sm text-red-800">{errorText(approveMutation.error)}</p>
            ) : null}
          </section>

          <section aria-labelledby="new-heading" className="space-y-2 border-t border-stone-200 pt-6">
            <h2 id="new-heading" className="text-lg text-stone-900">
              New since last review
            </h2>
            <p className="text-sm text-stone-600">{company.new_since_review_note}</p>
            {company.new_since_review.length > 0 ? (
              <ul className="space-y-3">
                {company.new_since_review.map((doc) => (
                  <li key={doc.document_id} className="border-b border-stone-100 pb-3 text-sm">
                    <p className="text-stone-900">{doc.title}</p>
                    <p className="text-stone-500">
                      {doc.reason}
                      {doc.indexed_at ? ` · ${formatWhen(doc.indexed_at)}` : ""}
                    </p>
                    <p className="text-stone-600">Source unavailable to open in the browser.</p>
                  </li>
                ))}
              </ul>
            ) : null}
            <label className="block text-sm text-stone-700" htmlFor="review-note">
              Review note, optional
              <input
                id="review-note"
                className="mt-1 w-full border border-stone-300 px-3 py-2 text-base"
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="min-h-11 border border-stone-800 px-3 py-2 text-sm disabled:opacity-50"
                disabled={reviewMutation.isPending}
                onClick={() => reviewMutation.mutate("unchanged")}
              >
                No thesis change
              </button>
              <button
                type="button"
                className="min-h-11 border border-stone-300 px-3 py-2 text-sm disabled:opacity-50"
                disabled={reviewMutation.isPending}
                onClick={() => reviewMutation.mutate("investigate")}
              >
                Needs investigation
              </button>
            </div>
            {reviewMutation.isError ? (
              <p className="text-sm text-red-800">{errorText(reviewMutation.error)}</p>
            ) : null}
          </section>

          <section aria-labelledby="ask-heading" className="space-y-3 border-t border-stone-200 pt-6">
            <h2 id="ask-heading" className="text-lg text-stone-900">
              Ask about this company
            </h2>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className="min-h-11 border border-stone-300 px-3 py-2 text-left text-sm"
                  onClick={() => setQuestion(preset)}
                >
                  {preset}
                </button>
              ))}
            </div>
            <label className="block text-sm text-stone-700" htmlFor="company-question">
              Your question
              <textarea
                id="company-question"
                className="mt-1 min-h-20 w-full border border-stone-300 bg-transparent px-3 py-2 text-base"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="min-h-11 border border-stone-800 px-4 py-2 text-sm disabled:opacity-50"
              disabled={askMutation.isPending || !question.trim()}
              onClick={() => ask(question)}
            >
              {askMutation.isPending ? "Asking…" : "Ask Grok"}
            </button>
            {askMutation.isError ? (
              <p className="text-sm text-red-800">{errorText(askMutation.error)}</p>
            ) : null}
            {askMutation.data ? (
              <div className="space-y-3 border border-stone-200 p-3">
                <h3 className="text-sm text-stone-500">Answer</h3>
                <p className="text-sm text-stone-800">{answerText || "No answer text was returned."}</p>
                {citations.length > 0 ? (
                  <>
                    <h3 className="text-sm text-stone-500">Evidence</h3>
                    <ul className="list-disc space-y-1 pl-5 text-sm text-stone-700">
                      {citations.map((item, index) => {
                        const row = item as Record<string, unknown>;
                        const path = typeof row.relative_path === "string" ? row.relative_path : "Source";
                        const page = typeof row.page === "number" ? ` page ${row.page}` : "";
                        return (
                          <li key={`${path}-${index}`}>
                            {path}
                            {page}. Original file is not available to open here.
                          </li>
                        );
                      })}
                    </ul>
                  </>
                ) : null}
                {uncertainty.length > 0 ? (
                  <>
                    <h3 className="text-sm text-stone-500">Uncertainty</h3>
                    <ul className="list-disc space-y-1 pl-5 text-sm text-stone-700">
                      {uncertainty.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </div>
            ) : null}
          </section>

          <section aria-labelledby="questions-heading" className="space-y-2 border-t border-stone-200 pt-6">
            <h2 id="questions-heading" className="text-lg text-stone-900">
              Open questions
            </h2>
            {company.questions.length === 0 ? (
              <p className="text-sm text-stone-600">No open questions.</p>
            ) : (
              <ul className="space-y-2">
                {company.questions.map((goal) => (
                  <li key={goal.goal_id} className="text-sm text-stone-800">
                    <p>{goal.title}</p>
                    {goal.rationale ? <p className="text-stone-600">{goal.rationale}</p> : null}
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              className="min-h-11 text-sm text-stone-700 underline-offset-2 hover:underline"
              onClick={() => setPanel("questions")}
            >
              View all
            </button>
          </section>
        </div>
      ) : null}

      {panel === "thesis" ? (
        <section className="space-y-3">
          <h2 className="text-lg text-stone-900">Save a thesis</h2>
          <p className="text-sm text-stone-600">
            Paste a memo from Gemini or ChatGPT. This stores a new version. It does not approve it.
          </p>
          <label className="block text-sm text-stone-700">
            Memo
            <textarea
              className="mt-1 min-h-32 w-full border border-stone-300 bg-transparent px-3 py-2 text-sm"
              value={thesisPaste}
              onChange={(e) => setThesisPaste(e.target.value)}
            />
          </label>
          <label className="block text-sm text-stone-700">
            Assumptions to watch, one per line
            <textarea
              className="mt-1 min-h-20 w-full border border-stone-300 bg-transparent px-3 py-2 text-sm"
              value={monitorPaste}
              onChange={(e) => setMonitorPaste(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="min-h-11 border border-stone-800 px-4 py-2 text-sm disabled:opacity-50"
            disabled={thesisMutation.isPending || !thesisPaste.trim()}
            onClick={() => thesisMutation.mutate()}
          >
            {thesisMutation.isPending ? "Saving…" : "Save thesis"}
          </button>
          {thesisMutation.isError ? (
            <p className="text-sm text-red-800">{errorText(thesisMutation.error)}</p>
          ) : null}
        </section>
      ) : null}

      {panel === "documents" && company ? (
        <section className="space-y-3">
          <h2 className="text-lg text-stone-900">Documents linked to this company</h2>
          {company.documents.length === 0 ? (
            <p className="text-sm text-stone-600">No documents are linked to this company yet.</p>
          ) : (
            <ul className="space-y-3">
              {company.documents.map((doc) => (
                <li key={doc.document_id} className="border-b border-stone-100 pb-3 text-sm">
                  <p className="text-stone-900">{doc.title}</p>
                  <p className="text-stone-500">{doc.relative_path}</p>
                  <p className="text-stone-600">Source unavailable to open in the browser.</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {panel === "questions" ? (
        <section className="space-y-3">
          <h2 className="text-lg text-stone-900">Questions for this company</h2>
          <p className="text-sm text-stone-600">
            These were saved for this company only. “Still open” means nobody has marked the question done.
          </p>
          {goalsQuery.isLoading ? (
            <p className="text-sm text-stone-500">Loading…</p>
          ) : (goalsQuery.data ?? []).filter((goal) => goal.status === "accepted" || goal.status === "proposed").length === 0 ? (
            <p className="text-sm text-stone-600">No open questions for this company.</p>
          ) : (
            <ul className="space-y-3">
              {(goalsQuery.data ?? [])
                .filter((goal) => goal.status === "accepted" || goal.status === "proposed")
                .map((goal) => (
                <li key={goal.goal_id} className="text-sm">
                  <p className="text-stone-900">{goal.title}</p>
                  <p className="text-xs text-stone-500">Still open</p>
                  {goal.rationale ? <p className="text-stone-600">{goal.rationale}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </div>
  );
}
