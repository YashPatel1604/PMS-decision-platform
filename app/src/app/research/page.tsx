import { Suspense } from "react";

import { ResearchAnalystView } from "@/components/research-analyst-view";

export default function ResearchPage() {
  return (
    <Suspense fallback={<p className="px-4 py-8 text-sm text-stone-600">Loading research…</p>}>
      <ResearchAnalystView />
    </Suspense>
  );
}
