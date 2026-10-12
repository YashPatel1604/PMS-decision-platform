"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { ResearchAnalystView } from "@/components/research-analyst-view";
import { ResearchHome } from "@/components/research-home";

export function ResearchPageClient() {
  const params = useSearchParams();
  const router = useRouter();
  const securityId = params.get("security_id")?.trim() ?? "";
  const view = params.get("view")?.trim() ?? "";
  const openCompany = Boolean(securityId) && view !== "tools";

  useEffect(() => {
    if (openCompany) {
      router.replace(`/research/company/${encodeURIComponent(securityId)}`);
    }
  }, [openCompany, router, securityId]);

  if (openCompany) {
    return <p className="px-4 py-8 text-sm text-stone-600">Opening company…</p>;
  }
  if (view === "tools") {
    return <ResearchAnalystView />;
  }
  return <ResearchHome />;
}
