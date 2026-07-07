"""`qmtcli fields` (item 4): static xtdata field-name reference dictionaries extracted from the doc
appendix by scripts/extract_doc_fields.py into src/qmtcli/xtdata_fields.json.

Fully offline: `fields` must never touch QMTGateway/xtdata at all, unlike every other data command.
"""

from __future__ import annotations

import json

import pytest

from qmtcli.cli import DATA_COMMAND_NAMES, _dispatch_fields_command, _handle_rpc_request, main
from qmtcli.gateway import QMTGateway

EXPECTED_KINDS = {
    "tick",
    "kline",
    "divid",
    "l2quote",
    "l2order",
    "l2transaction",
    "l2quoteaux",
    "l2orderqueue",
    "balance",
    "income",
    "cashflow",
    "pershareindex",
    "capital",
    "top10holder",
    "holdernum",
    "instrument",
}


def test_fields_tick_returns_nonempty_list_with_name_and_desc(capsys):
    assert main(["fields", "tick"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload
    for entry in payload:
        assert set(entry) == {"name", "desc"}
        assert entry["name"]


def test_fields_no_arg_lists_kinds_with_titles(capsys):
    assert main(["fields"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    assert EXPECTED_KINDS <= set(payload)
    assert all(isinstance(title, str) and title for title in payload.values())


def test_all_expected_kinds_present_with_nonempty_fields():
    catalog = _dispatch_fields_command(None)
    assert EXPECTED_KINDS <= set(catalog)
    for kind in EXPECTED_KINDS:
        fields = _dispatch_fields_command(kind)
        assert fields, f"{kind} parsed to zero fields"


def test_fields_unknown_kind_rejected_by_argparse_choices():
    with pytest.raises(SystemExit) as exc:
        main(["fields", "not-a-real-kind"])

    assert exc.value.code == 2


def test_fields_unknown_kind_direct_dispatch_raises_value_error():
    with pytest.raises(ValueError, match="unknown fields kind"):
        _dispatch_fields_command("not-a-real-kind")


def test_fields_unknown_kind_over_rpc_returns_clean_error():
    # RPC has no argparse choices restriction, so this exercises _dispatch_fields_command's own
    # ValueError through the normal RPC error envelope.
    response = _handle_rpc_request({"command": "fields", "kind": "not-a-real-kind"})

    assert response["ok"] is False
    assert "unknown fields kind" in response["error"]


def test_fields_over_rpc_no_kind_lists_kinds():
    response = _handle_rpc_request({"command": "fields"})

    assert response["ok"] is True
    assert EXPECTED_KINDS <= set(response["data"])


def test_fields_over_rpc_with_kind_returns_field_list():
    response = _handle_rpc_request({"command": "fields", "kind": "balance"})

    assert response["ok"] is True
    assert len(response["data"]) > 100  # Balance sheet has 100+ documented fields


def test_fields_never_calls_gateway(monkeypatch, capsys):
    """fields is special-cased before any gateway use; it must not call call_data."""

    def fail_if_called(*args, **kwargs):
        raise AssertionError("fields must not call QMTGateway.call_data")

    monkeypatch.setattr(QMTGateway, "call_data", fail_if_called)

    assert main(["fields", "tick"]) == 0
    assert main(["fields"]) == 0


def test_fields_is_not_routed_through_the_generic_data_command_dispatcher():
    assert "fields" not in DATA_COMMAND_NAMES


def test_fields_capabilities_entry_present():
    response = _handle_rpc_request({"command": "capabilities"})

    names = {c["name"] for c in response["data"]["commands"]}
    assert "fields" in names
    fields_entry = next(c for c in response["data"]["commands"] if c["name"] == "fields")
    assert fields_entry["requires_account"] is False
    assert fields_entry["danger"] == "safe"
