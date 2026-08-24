import { formatPct, formatPnL, formatPrice, toneClass, valueTone, type ValueTone } from "@/lib/format";

type FormattedValueProps = {
  value: number | null | undefined;
  kind: "pct" | "pnl" | "price";
  className?: string;
};

function formatByKind(value: number, kind: FormattedValueProps["kind"]): string {
  if (kind === "pct") return formatPct(value);
  if (kind === "pnl") return formatPnL(value);
  return formatPrice(value);
}

export function FormattedValue({ value, kind, className = "" }: FormattedValueProps) {
  if (value === null || value === undefined) {
    return <span className={`text-stone-400 ${className}`}>—</span>;
  }

  const tone: ValueTone = kind === "price" ? "neutral" : valueTone(value);
  return (
    <span className={`font-medium tabular-nums ${toneClass(tone)} ${className}`}>
      {formatByKind(value, kind)}
    </span>
  );
}

export function FormattedPct({
  value,
  below = false,
  suffix,
  className = "",
}: {
  value: number | null | undefined;
  below?: boolean;
  suffix?: string;
  className?: string;
}) {
  if (value === null || value === undefined) {
    return <span className={`text-stone-400 ${className}`}>—</span>;
  }

  const display = below
    ? value > 0
      ? `−${Math.abs(value).toFixed(2)}%`
      : `${value.toFixed(2)}%`
    : formatPct(value);
  const tone = below ? (value > 0 ? "negative" : "neutral") : valueTone(value);

  return (
    <span className={`tabular-nums ${toneClass(tone)} ${className}`}>
      {display}
      {suffix ? <span className="text-stone-500"> {suffix}</span> : null}
    </span>
  );
}
