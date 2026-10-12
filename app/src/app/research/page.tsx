import { Suspense } from "react";

import { ResearchPageClient } from "@/components/research-page-client";

export default function ResearchPage() {
  return (
    <Suspense fallback={<p className="px-4 py-8 text-sm text-stone-600">Loading research…</p>}>
      <ResearchPageClient />
    </Suspense>
  );
}
