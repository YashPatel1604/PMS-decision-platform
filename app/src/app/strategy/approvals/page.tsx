import { ApprovalInbox } from "@/components/approval-inbox";

export default function ApprovalsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <div>
        <h1 className="text-xl font-semibold text-stone-900">Approvals</h1>
        <p className="mt-1 text-sm text-stone-600">
          Review submitted portfolio changes. Official data updates only after approval.
        </p>
      </div>
      <ApprovalInbox />
    </div>
  );
}
