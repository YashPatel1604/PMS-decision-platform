"""Unit tests for BSE SAST / Insider disclosure normalization."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from pms_platform.market_data.bse_corporate_disclosures import (
    normalize_insider_row,
    normalize_sast_row,
)


def test_normalize_sast_row_resolves_isin() -> None:
    raw = {
        "ScripCode": None,
        "ComName": "APOLLO PIPES LIMITED EQ",
        "ProISIN": "INE126J01016",
        "PromName": "S Gupta Holding Private Limited",
        "PreHold": 2175014.0,
        "PerPreHold": 4.94,
        "QTYTrans": 403089,
        "PerQTY": 0.92,
        "PostHold": 2578103.0,
        "PerPostHold": 5.85,
        "DATETrans": "2026-08-05T00:00:00",
        "TransType": "Acquisition of shares - market",
        "Promoter_NonPromoter": "Promoter",
        "reg29_1_2": "29(1)",
        "transactiondisplay": "2026-08-06",
    }
    with patch(
        "pms_platform.market_data.bse_corporate_disclosures.resolve_bse_code",
        return_value="542534",
    ):
        row = normalize_sast_row(raw)
    assert row is not None
    assert row.kind == "sast"
    assert row.bse_code == "542534"
    assert row.disclosure_date == date(2026, 8, 5)
    assert row.quantity == Decimal("403089")
    assert row.regulation == "29(1)"


def test_normalize_insider_row() -> None:
    raw = {
        "Fld_ScripCode": 544444,
        "Companyname": "Glen Industries Ltd",
        "Fld_PromoterName": "Lalit Agrawal(HUF)",
        "Fld_PersonCatgName": "Promoter Group",
        "Fld_TransactionType": "Acquisition",
        "Fld_SecurityNo": 44400,
        "Fld_SecurityValue": "4966584.00",
        "Fld_PercentofShareholdingPre": "0.78",
        "Fld_PercentofShareholdingPost": "0.96",
        "Fld_StampDate": "2026-08-06T00:00:00",
        "ModeOfAquisation": "Market Purchase",
    }
    with patch(
        "pms_platform.market_data.bse_corporate_disclosures.resolve_bse_code",
        return_value="544444",
    ):
        row = normalize_insider_row(raw)
    assert row is not None
    assert row.kind == "insider"
    assert row.bse_code == "544444"
    assert row.disclosure_date == date(2026, 8, 6)
    assert row.value == Decimal("4966584.00")
    assert row.mode == "Market Purchase"
