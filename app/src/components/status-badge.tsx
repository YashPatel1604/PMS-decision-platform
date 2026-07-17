export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  const className =
    normalized === "OK"
      ? "bg-emerald-100 text-emerald-800"
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
