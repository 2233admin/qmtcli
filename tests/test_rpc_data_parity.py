"""RPC/server parity coverage for named data commands.

_handle_rpc_data routes named data commands (calendar, bars, ...) through the same
_dispatch_data_command() the CLI uses, so an agent driving qmtcli purely over rpc/server JSON gets
the same command surface as the CLI instead of being limited to status/doctor/data_call/account
commands.
"""

from __future__ import annotations

from typing import Any

import pytest

from qmtcli.cli import _handle_rpc_request, main
from qmtcli.gateway import QMTGateway


@pytest.fixture
def call_log(monkeypatch) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def fake_call_data(method: str, *args: Any, **kwargs: Any) -> Any:
        calls.append((method, args, kwargs))
        return {"method": method}

    monkeypatch.setattr(QMTGateway, "call_data", fake_call_data)
    return calls


# Each case pairs a CLI invocation with an equivalent RPC request body; both must produce the
# exact same call_data(method, *args, **kwargs) call.
RPC_PARITY_CASES = [
    (
        ["calendar", "SH"],
        {"command": "calendar", "market": "SH"},
    ),
    (
        ["bars", "600519.SH", "--period", "1d", "--count", "10"],
        {"command": "bars", "symbols": ["600519.SH"], "period": "1d", "count": 10},
    ),
    (
        ["l2-quote", "600519.SH"],
        {"command": "l2-quote", "symbol": "600519.SH"},
    ),
    (
        ["financials", "600519.SH", "--tables", "Balance"],
        {"command": "financials", "symbols": ["600519.SH"], "tables": ["Balance"]},
    ),
    (
        ["download", "history", "600519.SH", "--period", "1d"],
        {"command": "download", "target": "history", "symbols": ["600519.SH"], "period": "1d"},
    ),
    (
        ["instrument-detail", "600519.SH", "--complete"],
        {"command": "instrument-detail", "symbol": "600519.SH", "complete": True},
    ),
    (
        ["sector", "add", "MySector", "600519.SH"],
        {"command": "sector", "action": "add", "name": "MySector", "symbols": ["600519.SH"]},
    ),
    (
        ["sector", "create-folder", "MyGroup", "--parent", "我的自定义板块"],
        {
            "command": "sector",
            "action": "create-folder",
            "name": "MyGroup",
            "parent": "我的自定义板块",
        },
    ),
    (
        ["local-data", "600519.SH", "--period", "1d"],
        {"command": "local-data", "symbols": ["600519.SH"], "period": "1d"},
    ),
    (
        ["full-kline", "600519.SH", "--period", "1m"],
        {"command": "full-kline", "symbols": ["600519.SH"], "period": "1m"},
    ),
]


@pytest.mark.parametrize("argv,request_body", RPC_PARITY_CASES)
def test_rpc_named_data_command_matches_cli_call_data(call_log, argv, request_body):
    assert main(argv) == 0
    cli_call = call_log[0]
    call_log.clear()

    response = _handle_rpc_request(request_body)

    assert response["ok"] is True, response
    assert call_log == [cli_call]


MISSING_PARAM_CASES = [
    ({"command": "calendar"}, "requires market"),
    ({"command": "sector-stocks"}, "requires sector"),
    ({"command": "full-tick"}, "requires symbols"),
    ({"command": "bars"}, "requires symbols"),
    ({"command": "l2-quote"}, "requires symbol"),
    ({"command": "l2-order"}, "requires symbol"),
    ({"command": "l2-transaction"}, "requires symbol"),
    ({"command": "instrument-detail"}, "requires symbol"),
    ({"command": "instrument-type"}, "requires symbol"),
    ({"command": "trading-dates"}, "requires market"),
    ({"command": "divid-factors"}, "requires symbol"),
    ({"command": "cb-info"}, "requires symbol"),
    ({"command": "index-weight"}, "requires index_code"),
    ({"command": "financials"}, "requires symbols"),
    ({"command": "download"}, "requires target"),
    ({"command": "download", "target": "history"}, "requires symbols"),
    ({"command": "download", "target": "financials"}, "requires symbols"),
    ({"command": "sector"}, "requires action"),
    ({"command": "sector", "action": "not-a-real-action"}, "requires action"),
    ({"command": "sector", "action": "add"}, "requires name"),
    ({"command": "sector", "action": "add", "name": "MySector"}, "requires symbols"),
    ({"command": "sector", "action": "remove-stocks", "name": "MySector"}, "requires symbols"),
    ({"command": "sector", "action": "reset", "name": "MySector"}, "requires symbols"),
    ({"command": "sector", "action": "create-folder", "name": "MyGroup"}, "requires parent"),
    ({"command": "sector", "action": "create", "name": "MySector"}, "requires parent"),
    ({"command": "local-data"}, "requires symbols"),
    ({"command": "full-kline"}, "requires symbols"),
]


@pytest.mark.parametrize("request_body,expected_substring", MISSING_PARAM_CASES)
def test_rpc_missing_required_param_returns_ok_false(call_log, request_body, expected_substring):
    response = _handle_rpc_request(request_body)

    assert response["ok"] is False
    assert expected_substring in response["error"]
    assert call_log == []


def test_rpc_underscore_alias_full_tick_works(call_log):
    response = _handle_rpc_request({"command": "full_tick", "symbols": ["600519.SH"]})

    assert response["ok"] is True
    assert call_log == [("get_full_tick", (["600519.SH"],), {})]


def test_rpc_underscore_alias_sector_stocks_works(call_log):
    response = _handle_rpc_request({"command": "sector_stocks", "sector": "沪深A股"})

    assert response["ok"] is True
    assert call_log == [("get_stock_list_in_sector", ("沪深A股",), {})]


def test_rpc_underscore_alias_local_data_works(call_log):
    response = _handle_rpc_request({"command": "local_data", "symbols": ["600519.SH"]})

    assert response["ok"] is True
    assert call_log[0][0] == "get_local_data"


def test_rpc_underscore_alias_full_kline_works(call_log):
    response = _handle_rpc_request({"command": "full_kline", "symbols": ["600519.SH"]})

    assert response["ok"] is True
    assert call_log[0][0] == "get_full_kline"


def test_rpc_dash_form_still_works(call_log):
    response = _handle_rpc_request({"command": "sector-list"})

    assert response["ok"] is True
    assert call_log == [("get_sector_list", (), {})]


def test_rpc_data_call_is_not_treated_as_a_named_data_command(call_log):
    # "data_call"/"data-call" is handled by its own dedicated branch (native args/kwargs, no JSON
    # string parsing) and must not be swallowed by the generic named-data-command routing.
    response = _handle_rpc_request(
        {"command": "data_call", "method": "get_sector_list", "args": [], "kwargs": {}}
    )

    assert response["ok"] is True
    assert call_log == [("get_sector_list", (), {})]
