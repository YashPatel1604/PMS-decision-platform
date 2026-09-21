"use client";

import { DailyEditPanel } from "@/components/daily-edit-panel";
import type { DailyEditCategory } from "@/lib/api";

const PANELS: { category: DailyEditCategory; title: string }[] = [
  { category: "sca_llp", title: "SCA LLP" },
  { category: "pivot_points", title: "Pivot Points" },
  { category: "client_portfolio", title: "Client Portfolio" },
  { category: "charts", title: "Charts" },
];

export function DailyEditSheetsView() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Sheets</h2>
        <p className="mt-2 max-w-2xl text-stone-600">
          Upload a new workbook, review the preview, then confirm. Confirmed numbers become the
          live source — no separate admin approval.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {PANELS.map((panel) => (
          <DailyEditPanel key={panel.category} category={panel.category} title={panel.title} />
        ))}
      </div>
    </div>
  );
}
