from __future__ import annotations

import io
import json
import sys

from qmtcli.cli import main


def _json_out(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_capabilities_cli_is_agent_readable(capsys):
    assert main(["capabilities"]) == 0

    response = _json_out(capsys)
    assert response["ok"] is True
    assert response["data"]["protocol"] == "qmtcli.agent.v1"
    names = {command["name"] for command in response["data"]["commands"]}
    assert {
        "status",
        "doctor",
        "data_call",
        "calendar",
        "sector-list",
        "sector-stocks",
        "full-tick",
        "bars",
        "l2-quote",
        "l2-order",
        "l2-transaction",
        "asset",
        "positions",
        "orders",
        "trades",
        "buy",
        "sell",
        "cancel",
        "trade_call",
    } <= names
    assert {"safe", "escape_hatch", "places_order"} <= {
        command["danger"] for command in response["data"]["commands"]
    }


def test_schema_cli_documents_response_contract(capsys):
    assert main(["schema"]) == 0

    response = _json_out(capsys)
    assert response["ok"] is True
    assert "ok" in response["data"]["response"]
    assert response["data"]["server"]["network"] is False


def test_examples_cli_returns_parseable_requests(capsys):
    assert main(["examples"]) == 0

    response = _json_out(capsys)
    assert response["ok"] is True
    assert response["data"]["status"]["command"] == "status"
    assert response["data"]["buy"]["command"] == "buy"


def test_agent_metadata_available_over_rpc(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"id":"a1","command":"capabilities"}'))

    assert main(["rpc"]) == 0

    response = _json_out(capsys)
    assert response["ok"] is True
    assert response["id"] == "a1"
    assert response["data"]["protocol"] == "qmtcli.agent.v1"


def test_agent_metadata_available_over_jsonl_server(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"id":1,"command":"schema"}\n'))

    assert main(["server"]) == 0

    response = json.loads(capsys.readouterr().out)
    assert response["ok"] is True
    assert response["id"] == 1
    assert response["data"]["server"]["transport"] == "stdin/stdout JSONL"
