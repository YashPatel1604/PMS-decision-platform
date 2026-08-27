"use client";

export type PortfolioView = "official" | "mine";

export function ViewModeToggle({
  view,
  onChange,
  disabled,
}: {
  view: PortfolioView;
  onChange: (view: PortfolioView) => void;
  disabled?: boolean;
}) {
  return (
    <div
      className="inline-flex rounded-lg border border-stone-200 bg-stone-50 p-0.5 text-xs font-medium"
      role="group"
      aria-label="Portfolio view"
    >
      {(
        [
          ["official", "Official"],
          ["mine", "My Working"],
        ] as const
      ).map(([key, label]) => (
        <button
          key={key}
          type="button"
          disabled={disabled}
          onClick={() => onChange(key)}
          className={`rounded-md px-3 py-1.5 transition-colors ${
            view === key
              ? "bg-white text-stone-900 shadow-sm"
              : "text-stone-600 hover:text-stone-900"
          } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
