"""Parse NSE integrated/legacy financial XBRL into normalized facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

from pms_platform.market_data.bse_financial_results import fiscal_label

_INR_TO_CRORE = Decimal("10000000")
_PL_TAGS = (
    "RevenueFromOperations",
    "Revenue",
    "ProfitOrLossAttributableToOwnersOfParent",
    "ProfitLossForPeriod",
    "ProfitLossForPeriodFromContinuingOperations",
    "ProfitForThePeriod",
    "ProfitBeforeExceptionalItemsAndTax",
    "ProfitBeforeTax",
)


@dataclass(frozen=True)
class NseQuarterlyFacts:
    period_end: date
    sales: Decimal | None
    pat: Decimal | None
    opm: Decimal | None
    npm: Decimal | None


@dataclass(frozen=True)
class NseAnnualFacts:
    fiscal_year: int
    period_end: date
    total_assets: Decimal | None
    total_equity: Decimal | None
    total_debt: Decimal | None
    cash_and_equivalents: Decimal | None
    finance_costs: Decimal | None
    current_assets: Decimal | None
    current_liabilities: Decimal | None
    pat: Decimal | None
    ebit: Decimal | None
    sales: Decimal | None
    roce: Decimal | None
    roe: Decimal | None
    roa: Decimal | None
    debt_to_equity: Decimal | None
    interest_coverage: Decimal | None
    current_ratio: Decimal | None


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_dec(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "—", "na", "n/a"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _to_crores(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return (value / _INR_TO_CRORE).quantize(Decimal("0.01"))


def _divide(num: Decimal | None, den: Decimal | None) -> Decimal | None:
    if num is None or den is None or den == 0:
        return None
    return (num / den).quantize(Decimal("0.0001"))


def _contexts(root: ET.Element) -> dict[str, tuple[date | None, date | None, date | None]]:
    """Map context id -> (start, end, instant)."""
    out: dict[str, tuple[date | None, date | None, date | None]] = {}
    for elem in root.iter():
        if _local(elem.tag) != "context":
            continue
        ctx_id = elem.get("id", "")
        start_d: date | None = None
        end_d: date | None = None
        instant_d: date | None = None
        for child in elem.iter():
            tag = _local(child.tag)
            if tag == "startDate" and child.text:
                try:
                    start_d = date.fromisoformat(child.text.strip())
                except ValueError:
                    pass
            elif tag == "endDate" and child.text:
                try:
                    end_d = date.fromisoformat(child.text.strip())
                except ValueError:
                    pass
            elif tag == "instant" and child.text:
                try:
                    instant_d = date.fromisoformat(child.text.strip())
                except ValueError:
                    pass
        out[ctx_id] = (start_d, end_d, instant_d)
    return out


def _instant_context_for_period(
    contexts: dict[str, tuple[date | None, date | None, date | None]],
    period_end: date,
) -> str | None:
    matches = [ctx_id for ctx_id, (_, _, instant) in contexts.items() if instant == period_end]
    if not matches:
        return None

    def _rank(ctx_id: str) -> tuple[int, str]:
        lowered = ctx_id.casefold()
        penalty = sum(1 for bad in ("reportable", "segment", "expenses", "auditor", "items") if bad in lowered)
        return (penalty, ctx_id)

    return sorted(matches, key=_rank)[0]


def _context_for_period(contexts: dict[str, tuple[date | None, date | None, date | None]], period_end: date) -> str | None:
    candidates = [
        ctx_id
        for ctx_id, (_, end, _) in contexts.items()
        if end == period_end
    ]
    if not candidates:
        return None

    def _rank(ctx_id: str) -> tuple[int, int, str]:
        lowered = ctx_id.casefold()
        penalty = 0
        for bad in ("reportable", "segment", "expenses", "auditor"):
            if bad in lowered:
                penalty += 1
        duration = 0
        start, end, _ = contexts[ctx_id]
        if start and end:
            duration = (end - start).days
        return (penalty, -duration, ctx_id)

    return sorted(candidates, key=_rank)[0]


def _facts_for_context(root: ET.Element, ctx_id: str) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for elem in root.iter():
        if elem.get("contextRef") != ctx_id:
            continue
        tag = _local(elem.tag)
        val = _parse_dec(elem.text)
        if val is not None:
            out[tag] = val
    return out


def _collect_pl_by_context(root: ET.Element) -> dict[str, dict[str, Decimal]]:
    by_ctx: dict[str, dict[str, Decimal]] = {}
    for elem in root.iter():
        ctx = elem.get("contextRef")
        if not ctx:
            continue
        tag = _local(elem.tag)
        if tag not in _PL_TAGS and tag not in {
            "Assets",
            "Equity",
            "EquityAttributableToOwnersOfParent",
            "BorrowingsNoncurrent",
            "BorrowingsCurrent",
            "Borrowings",
            "CashAndCashEquivalents",
            "FinanceCosts",
            "CurrentAssets",
            "CurrentLiabilities",
        }:
            continue
        val = _parse_dec(elem.text)
        if val is None:
            continue
        by_ctx.setdefault(ctx, {})[tag] = val
    return by_ctx


def _legacy_pl_context(by_ctx: dict[str, dict[str, Decimal]]) -> str | None:
    """Legacy NSE filings reference undefined OneD/FourD contexts — prefer Four* (full year)."""
    candidates: list[tuple[tuple[int, Decimal], str]] = []
    for ctx_ref, facts in by_ctx.items():
        revenue = facts.get("RevenueFromOperations") or facts.get("Revenue")
        if revenue is None:
            continue
        rank = (1 if ctx_ref.startswith("Four") else 0, revenue)
        candidates.append((rank, ctx_ref))
    if not candidates:
        return None
    return max(candidates)[1]


def _facts_from_pl_context(
    root: ET.Element,
    contexts: dict[str, tuple[date | None, date | None, date | None]],
    period_end: date,
) -> dict[str, Decimal]:
    by_ctx = _collect_pl_by_context(root)
    ctx = _context_for_period(contexts, period_end)
    if ctx is None:
        pl_ctx: str | None = None
        best_days = 0
        for ctx_id, (start, end, _) in contexts.items():
            if end == period_end and start and (end - start).days > best_days:
                best_days = (end - start).days
                pl_ctx = ctx_id
        ctx = pl_ctx
    if ctx is None:
        ctx = _legacy_pl_context(by_ctx)
    if ctx is None:
        return {}
    f = _facts_for_context(root, ctx)
    instant_ctx = _instant_context_for_period(contexts, period_end)
    if instant_ctx and instant_ctx != ctx:
        f = {**f, **_facts_for_context(root, instant_ctx)}
    if instant_ctx:
        f = {**_facts_for_context(root, instant_ctx), **f}
    has_pl = any(
        f.get(k) is not None
        for k in ("RevenueFromOperations", "Revenue", "ProfitLossForPeriod", "ProfitOrLossAttributableToOwnersOfParent")
    )
    if not has_pl:
        legacy_ctx = _legacy_pl_context(by_ctx)
        if legacy_ctx:
            f = {**by_ctx.get(legacy_ctx, {}), **f}
    return f


def _annual_facts_from_fields(f: dict[str, Decimal], *, period_end: date) -> NseAnnualFacts | None:
    revenue = f.get("RevenueFromOperations") or f.get("Revenue")
    sales = _to_crores(revenue)
    total_assets = _to_crores(f.get("Assets"))
    total_equity = _to_crores(f.get("Equity") or f.get("EquityAttributableToOwnersOfParent"))
    debt = f.get("BorrowingsNoncurrent", Decimal("0")) + f.get("BorrowingsCurrent", Decimal("0"))
    total_debt = _to_crores(debt if debt else f.get("Borrowings"))
    cash = _to_crores(f.get("CashAndCashEquivalents"))
    finance_costs = _to_crores(f.get("FinanceCosts"))
    current_assets = _to_crores(f.get("CurrentAssets"))
    current_liabilities = _to_crores(f.get("CurrentLiabilities"))
    pat = _to_crores(
        f.get("ProfitOrLossAttributableToOwnersOfParent")
        or f.get("ProfitLossForPeriod")
        or f.get("ProfitForThePeriod")
    )
    ebit = _to_crores(f.get("ProfitBeforeExceptionalItemsAndTax") or f.get("ProfitBeforeTax"))
    if sales is None and pat is None and total_assets is None and total_equity is None:
        return None
    capital_employed = (
        total_assets - current_liabilities
        if total_assets is not None and current_liabilities is not None
        else None
    )
    roce = _divide(ebit, capital_employed)
    if roce is not None:
        roce = (roce * 100).quantize(Decimal("0.0001"))
    roe = _divide(pat, total_equity)
    if roe is not None:
        roe = (roe * 100).quantize(Decimal("0.0001"))
    roa = _divide(pat, total_assets)
    if roa is not None:
        roa = (roa * 100).quantize(Decimal("0.0001"))
    debt_to_equity = _divide(total_debt, total_equity)
    interest_coverage = _divide(ebit, finance_costs)
    current_ratio = _divide(current_assets, current_liabilities)
    fiscal_year, _ = fiscal_label(period_end)
    return NseAnnualFacts(
        fiscal_year=fiscal_year,
        period_end=period_end,
        total_assets=total_assets,
        total_equity=total_equity,
        total_debt=total_debt,
        cash_and_equivalents=cash,
        finance_costs=finance_costs,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        pat=pat,
        ebit=ebit,
        sales=sales,
        roce=roce,
        roe=roe,
        roa=roa,
        debt_to_equity=debt_to_equity,
        interest_coverage=interest_coverage,
        current_ratio=current_ratio,
    )


def parse_quarterly_xbrl(xml_text: str, *, period_end: date) -> NseQuarterlyFacts | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    contexts = _contexts(root)
    ctx_ids = [
        ctx_id
        for ctx_id, (_, end, _) in contexts.items()
        if end == period_end
    ]
    if not ctx_ids:
        ctx_ids = [_context_for_period(contexts, period_end) or ""]
    ctx_ids = [c for c in ctx_ids if c]
    if not ctx_ids:
        return None

    best: NseQuarterlyFacts | None = None
    for ctx in sorted(ctx_ids, key=lambda c: ("reportable" in c.casefold(), c)):
        f = _facts_for_context(root, ctx)
        revenue = f.get("RevenueFromOperations") or f.get("Revenue")
        pat = (
            f.get("ProfitOrLossAttributableToOwnersOfParent")
            or f.get("ProfitLossForPeriod")
            or f.get("ProfitLossForPeriodFromContinuingOperations")
        )
        if revenue is None and pat is None:
            continue
        pbei = f.get("ProfitBeforeExceptionalItemsAndTax") or f.get("ProfitBeforeTax")
        sales = _to_crores(revenue)
        pat_cr = _to_crores(pat)
        opm = None
        if pbei is not None and revenue not in (None, 0):
            opm = ((pbei / revenue) * Decimal("100")).quantize(Decimal("0.01"))
        npm = None
        if pat is not None and revenue not in (None, 0):
            npm = ((pat / revenue) * Decimal("100")).quantize(Decimal("0.01"))
        best = NseQuarterlyFacts(period_end=period_end, sales=sales, pat=pat_cr, opm=opm, npm=npm)
        if revenue is not None:
            return best
    return best


def parse_annual_xbrl(xml_text: str, *, period_end: date) -> NseAnnualFacts | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    contexts = _contexts(root)
    f = _facts_from_pl_context(root, contexts, period_end)
    return _annual_facts_from_fields(f, period_end=period_end)


def parse_annual_comparative_prior(xml_text: str, *, period_end: date) -> NseAnnualFacts | None:
    """Extract prior-year comparative P&L from an annual report (e.g. FY2022 report → FY2021 base)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    prior_end = date(period_end.year - 1, 3, 31)
    contexts = _contexts(root)
    candidates = [
        ctx_id
        for ctx_id, (_, end, _) in contexts.items()
        if end == prior_end
    ]
    if not candidates:
        return None

    def _rank(ctx_id: str) -> tuple[int, int, str]:
        start, end, _ = contexts[ctx_id]
        duration = (end - start).days if start and end else 0
        lowered = ctx_id.casefold()
        penalty = sum(1 for bad in ("reportable", "segment", "expenses", "auditor") if bad in lowered)
        return (penalty, -duration, ctx_id)

    ctx = sorted(candidates, key=_rank)[0]
    f = _facts_for_context(root, ctx)
    return _annual_facts_from_fields(f, period_end=prior_end)
