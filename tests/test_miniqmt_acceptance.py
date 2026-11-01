"""Acceptance must reject false successes and keep private account data out of receipts."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "miniqmt_acceptance",
    Path(__file__).resolve().parents[1] / "experiments" / "accept_miniqmt.py",
)
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def snapshot():
    return {
        "asset": {
            "account_id": "PRIVATE_ACCOUNT",
            "cash": 1234567.89,
            "frozen_cash": 0.0,
            "market_value": 1.0,
            "total_asset": 1234568.89,
        },
        "positions": [{"account_id": "PRIVATE_ACCOUNT", "volume": 2**33}],
        "orders": [],
        "trades": [],
        "meta": {
            "atomic": False,
            "native_generation": 1,
            "event_sequence_available": False,
        },
    }


def test_acceptance_receipt_contains_counts_and_flags_without_account_or_amounts():
    result = acceptance.summarize_snapshot(snapshot(), "PRIVATE_ACCOUNT")
    assert result["counts"] == {"positions": 1, "orders": 0, "trades": 0}
    assert result["native_generation"] == 1
    assert result["asset_amounts_finite"] is True
    encoded = json.dumps(result)
    assert "PRIVATE_ACCOUNT" not in encoded
    assert "1234567" not in encoded


@pytest.mark.parametrize("section", ["positions", "orders", "trades"])
def test_missing_sections_are_not_successful_empty_data(section):
    data = snapshot()
    del data[section]
    with pytest.raises(ValueError, match="snapshot"):
        acceptance.summarize_snapshot(data, "PRIVATE_ACCOUNT")


def test_wrong_identity_nonfinite_amounts_and_invalid_generation_are_rejected():
    data = snapshot()
    with pytest.raises(ValueError, match="identity"):
        acceptance.summarize_snapshot(data, "OTHER_ACCOUNT")
    data["asset"]["cash"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        acceptance.summarize_snapshot(data, "PRIVATE_ACCOUNT")
    data = snapshot()
    data["meta"]["native_generation"] = 0
    with pytest.raises(ValueError, match="generation"):
        acceptance.summarize_snapshot(data, "PRIVATE_ACCOUNT")


def test_mismatched_position_identity_is_rejected_without_disclosing_the_identifier():
    data = snapshot()
    data["positions"][0]["account_id"] = "UNEXPECTED_ACCOUNT"
    with pytest.raises(ValueError, match="identity") as caught:
        acceptance.summarize_snapshot(data, "PRIVATE_ACCOUNT")
    assert "UNEXPECTED_ACCOUNT" not in str(caught.value)


@pytest.mark.parametrize("field,value", [("atomic", True), ("event_sequence_available", True)])
def test_query_snapshot_cannot_claim_atomicity_or_an_event_cursor(field, value):
    data = snapshot()
    data["meta"][field] = value
    with pytest.raises(ValueError, match="consistency"):
        acceptance.summarize_snapshot(data, "PRIVATE_ACCOUNT")
