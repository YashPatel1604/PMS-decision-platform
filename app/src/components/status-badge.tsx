export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  const className =
    normalized === "OK"
      ? "bg-emerald-100 text-emerald-800"
      : normalized === "WELL_TIMED_EXIT"
        ? "bg-emerald-100 text-emerald-900 ring-1 ring-emerald-200"
        : normalized === "EXIT_TOO_EARLY"
          ? "bg-orange-100 text-orange-900 ring-1 ring-orange-200"
          : normalized === "EXIT_TOO_LATE"
            ? "bg-red-100 text-red-900 ring-1 ring-red-200"
            : normalized === "MIXED_EVIDENCE"
              ? "bg-violet-100 text-violet-900 ring-1 ring-violet-200"
              : normalized === "TOO_RECENT_TO_JUDGE"
                ? "bg-sky-100 text-sky-900 ring-1 ring-sky-200"
      : normalized.includes("INSUFFICIENT")
        ? "bg-amber-100 text-amber-900"
        : normalized.includes("LATE") || normalized.includes("ROTATION")
          ? "bg-red-100 text-red-900"
          : normalized.includes("GAVE_BACK")
            ? "bg-rose-100 text-rose-900"
            : normalized.includes("PREMATURE") || normalized.includes("LEFT_STOCK")
          ? "bg-orange-100 text-orange-900"
          : normalized.includes("INDEX_OUTPERFORMED") ||
              normalized.includes("PORTFOLIO_OUTPERFORMED")
            ? "bg-sky-100 text-sky-900"
            : normalized.includes("REDEPLOYMENT")
              ? "bg-violet-100 text-violet-900"
              : normalized.includes("GOOD") || normalized.includes("LOSS_AVOIDED")
                ? "bg-emerald-100 text-emerald-800"
                : "bg-stone-100 text-stone-700";

  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}
