from __future__ import annotations

import argparse
import io
import json
import sys

from qmtcli.cli import AGENT_CAPABILITIES, build_parser, main


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
        "download",
        "calendar",
        "sector-list",
        "sector-stocks",
        "full-tick",
        "bars",
        "l2-quote",
        "l2-order",
        "l2-transaction",
        "instrument-detail",
        "instrument-type",
        "trading-dates",
        "divid-factors",
        "holidays",
        "period-list",
        "ipo-info",
        "cb-info",
        "etf-info",
        "index-weight",
        "financials",
        "asset",
        "positions",
        "orders",
        "trades",
        "buy",
        "sell",
        "cancel",
        "trade_call",
    } <= names
    assert {"safe", "escape_hatch", "downloads_data", "places_order"} <= {
        command["danger"] for command in response["data"]["commands"]
    }


def _registered_subcommand_names() -> set[str]:
    parser = build_parser()
    for action in parser._actions:  # noqa: SLF001 - argparse exposes no public accessor.
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return set(action.choices.keys())
    return set()


def test_capabilities_commands_match_registered_subparsers():
    subcommands = _registered_subcommand_names()
    for command in AGENT_CAPABILITIES["commands"]:
        if command.get("transports") == ["server"]:
            # subscribe/subscribe_whole/unsubscribe are rpc/server-only by design; they have no
            # argparse subcommand of their own.
            continue
        cli_name = command.get("cli_command", command["name"])
        assert cli_name in subcommands, f"{cli_name!r} has no matching registered subparser"


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
