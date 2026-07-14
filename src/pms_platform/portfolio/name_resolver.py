"""Map snapshot stock labels to Security Master portfolio names."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import Security

# Snapshot workbooks use abbreviated labels that differ from the Security Master.
SNAPSHOT_NAME_ALIASES: dict[str, str] = {
    "Amaraja": "Amara Raja",
    "Balrampur": "BalrampurChini",
    "BirlaNu": "HIL",
    "Dynamatic": "Dynamatic Tech",
    "DynamaticTech": "Dynamatic Tech",
    "EicherMotors": "Eicher Motors",
    "J&Kbank": "JKBank",
    "LiquidBees": "LIQUID",
    "LiquidCase": "LIQUID",
    "LloydElec": "Llyod Electric",
    "MotilalOFS": "MOSL",
    "NIIT Tech": "NIITTech",
    "NeulandLab": "Neuland Labs",
    "Praj": "PrajInds",
    "RamcoSys": "Ramco Systems",
    "StridesArco": "Strides",
    "TV18Broadcast": "TV18",
    "TataGlobal": "Tata Global",
}

LIQUID_SNAPSHOT_NAMES = frozenset({"LiquidBees", "LiquidCase", "Liquid"})


def normalize_name(value: str) -> str:
    """Normalize a name for fuzzy comparison."""
    return value.lower().replace(" ", "").replace("&", "").replace("-", "")


def resolve_snapshot_name(snapshot_name: str, securities: list[Security]) -> str | None:
    """Resolve a snapshot label to a Security Master portfolio name."""
    if snapshot_name in LIQUID_SNAPSHOT_NAMES:
        return "LIQUID"

    if snapshot_name in SNAPSHOT_NAME_ALIASES:
        return SNAPSHOT_NAME_ALIASES[snapshot_name]

    portfolio_names = {security.portfolio_name for security in securities}
    if snapshot_name in portfolio_names:
        return snapshot_name

    normalized = normalize_name(snapshot_name)
    for security in securities:
        if normalize_name(security.portfolio_name) == normalized:
            return security.portfolio_name
        if (
            security.current_nse_symbol
            and normalize_name(security.current_nse_symbol) == normalized
        ):
            return security.portfolio_name
        if (
            security.historical_nse_symbol
            and normalize_name(security.historical_nse_symbol) == normalized
        ):
            return security.portfolio_name

    for security in securities:
        master_norm = normalize_name(security.portfolio_name)
        if master_norm.startswith(normalized) or normalized.startswith(master_norm):
            return security.portfolio_name

    return None


def build_name_lookup(session: Session) -> dict[str, Security]:
    """Build a portfolio-name lookup from the Security Master."""
    securities = list(session.scalars(select(Security)).all())
    return {security.portfolio_name: security for security in securities}


def resolve_snapshot_security_id(
    snapshot_name: str,
    securities: list[Security],
    name_lookup: dict[str, Security],
) -> tuple[str | None, str | None]:
    """Resolve a snapshot label to ``(security_id, portfolio_name)``."""
    portfolio_name = resolve_snapshot_name(snapshot_name, securities)
    if portfolio_name is None:
        return None, None
    if portfolio_name == "LIQUID":
        return None, "LIQUID"
    security = name_lookup.get(portfolio_name)
    if security is None:
        return None, portfolio_name
    return security.security_id, security.portfolio_name
