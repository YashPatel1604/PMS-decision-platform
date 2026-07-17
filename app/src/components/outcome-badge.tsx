/** Outcome badge with optional underwater-history hint. */

export function OutcomeBadge({
  outcome,
  lossHoldPattern,
}: {
  outcome: string;
  lossHoldPattern?: string | null;
}) {
  const normalized = outcome.toUpperCase();
  const className =
    normalized === "PROFIT_STOCK"
      ? lossHoldPattern === "RECOVERED_AFTER_LONG_LOSS"
        ? "bg-teal-100 text-teal-900 ring-1 ring-teal-200"
        : "bg-emerald-100 text-emerald-900 ring-1 ring-emerald-200"
      : normalized === "LOSS_STOCK"
        ? "bg-red-100 text-red-900 ring-1 ring-red-200"
        : "bg-stone-100 text-stone-700 ring-1 ring-stone-200";

  const label =
    normalized === "PROFIT_STOCK"
      ? lossHoldPattern === "RECOVERED_AFTER_LONG_LOSS"
        ? "Profit · was below buy cost 1+ yr"
        : "Profit stock"
      : normalized === "LOSS_STOCK"
        ? "Loss stock"
        : "Breakeven";

  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      {label}
    </span>
  );
}
