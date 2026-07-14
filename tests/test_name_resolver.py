"""Name resolver tests."""

from pms_platform.models import Security
from pms_platform.portfolio.name_resolver import resolve_snapshot_name


def test_resolve_snapshot_name_exact_and_alias() -> None:
    """Resolver handles exact names, aliases, and liquid labels."""
    securities = [
        Security(
            security_id="SEC001",
            portfolio_name="Dynamatic Tech",
            current_nse_symbol="DYNAMATECH",
        )
    ]
    assert resolve_snapshot_name("Dynamatic Tech", securities) == "Dynamatic Tech"
    assert resolve_snapshot_name("Dynamatic", securities) == "Dynamatic Tech"
    assert resolve_snapshot_name("LiquidCase", securities) == "LIQUID"
