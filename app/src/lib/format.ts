export type ValueTone = "positive" | "negative" | "neutral";

export function valueTone(value: number | null | undefined): ValueTone {
  if (value === null || value === undefined || Number.isNaN(value)) return "neutral";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

export function toneClass(tone: ValueTone): string {
  if (tone === "positive") return "text-emerald-700";
  if (tone === "negative") return "text-red-700";
  return "text-stone-700";
}

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const inrPriceFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat("en-IN");

export function formatNum(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPct(
  value: number | null | undefined,
  digits = 2,
  options?: { signed?: boolean },
): string {
  if (value === null || value === undefined) return "—";
  const signed = options?.signed ?? true;
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}%`;
}

export function formatPp(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)} pp`;
}

export function formatXirr(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const pct = value * 100;
  const prefix = pct > 0 ? "+" : "";
  return `${prefix}${pct.toFixed(2)}% p.a.`;
}

export function formatInr(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return inrFormatter.format(value);
}

/** Stock prices — ₹ with two decimal places. */
export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return inrPriceFormatter.format(value);
}

/** Signed P&L in rupees, e.g. +₹12,34,567 or −₹45,000. */
export function formatPnL(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const abs = inrFormatter.format(Math.abs(value));
  if (value > 0) return `+${abs}`;
  if (value < 0) return `−${abs}`;
  return abs;
}

export function formatYears(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const unit = Math.abs(value) === 1 ? "yr" : "yrs";
  return `${value.toFixed(digits)} ${unit}`;
}

export function formatDays(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${numberFormatter.format(value)} days`;
}

export function formatYearsFromDays(days: number | null | undefined, digits = 2): string {
  if (days === null || days === undefined) return "—";
  const years = days / 365.25;
  const unit = Math.abs(years) === 1 ? "yr" : "yrs";
  return `${years.toFixed(digits)} ${unit}`;
}

export function formatHoldAfterFirstLoss(
  exitOutcome: string,
  firstBelowCostDate: string | null | undefined,
  calendarDays: number | null | undefined,
  tradingDays: number | null | undefined,
  lossHoldPattern: string | null | undefined,
): string {
  if (exitOutcome === "PROFIT_STOCK") {
    if (lossHoldPattern === "RECOVERED_AFTER_LONG_LOSS" && firstBelowCostDate && calendarDays) {
      const since = formatDate(firstBelowCostDate);
      const calendarYears = formatYearsFromDays(calendarDays);
      const trading =
        tradingDays !== null && tradingDays !== undefined
          ? `${numberFormatter.format(tradingDays)} trading days`
          : null;
      return `Below first buy 1+ yr then profit · since ${since} · ${calendarYears} (${formatDays(calendarDays)}${trading ? ` · ${trading}` : ""})`;
    }
    return "Sold at profit — never below first buy for 1+ year";
  }
  if (exitOutcome !== "LOSS_STOCK") {
    return "—";
  }
  if (!firstBelowCostDate || calendarDays === null || calendarDays === undefined) {
    return "Loss stock — recovered above cost before exit";
  }

  const since = formatDate(firstBelowCostDate);
  const calendarYears = formatYearsFromDays(calendarDays);
  const trading =
    tradingDays !== null && tradingDays !== undefined
      ? `${numberFormatter.format(tradingDays)} trading days`
      : null;
  const patternLabel =
    lossHoldPattern === "RODE_WINNER_DOWN"
      ? "Rode winner down"
      : lossHoldPattern === "STAYED_UNDERWATER"
        ? "Stayed underwater"
        : "Final underwater stretch";
  return `${patternLabel} · since ${since} · ${calendarYears} (${formatDays(calendarDays)}${trading ? ` · ${trading}` : ""})`;
}

export function outcomeLabel(outcome: string | null | undefined): string {
  if (!outcome) return "—";
  if (outcome === "PROFIT_STOCK") return "Profit stock";
  if (outcome === "LOSS_STOCK") return "Loss stock";
  return "Breakeven";
}

export function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function assessmentLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replaceAll("_", " ");
}

export function formatExcessLabel(value: number | null | undefined, benchmark = "BSE SmallCap"): string {
  if (value === null || value === undefined) return "—";
  return `${formatPct(value)} vs ${benchmark}`;
}
