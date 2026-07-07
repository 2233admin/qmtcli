"""Coverage for the named read-only XtQuantTrader query commands added in this wave.

Each command in TRADE_QUERY_COMMANDS maps 1:1 onto QMTGateway.call_trader(method,
with_account=...), reached through QMTGateway.connect(subscribe=...). Three of them
(ipo-data, account-infos, account-status) wrap methods that take no account argument at all, so
--account is optional for them and connect() is asked to skip trader.subscribe().
"""

from __future__ import annotations

import importlib.machinery
import sys
import types
from typing import Any

import pytest

from qmtcli.cli import (
    ACCOUNT_OPTIONAL_COMMANDS,
    TRADE_QUERY_COMMANDS,
    _handle_rpc_request,
    main,
)
from qmtcli.gateway import QMTConnection, QMTGateway


@pytest.fixture
def gateway_spy(monkeypatch) -> dict[str, Any]:
    """Fake QMTGateway.connect/call_trader that record how they were invoked."""
    state: dict[str, Any] = {"connect_calls": [], "call_trader_calls": []}

    def fake_connect(self, subscribe: bool = True) -> None:
        state["connect_calls"].append(
            {"account_id": self.connection.account_id, "subscribe": subscribe}
        )
        self.trader = object()
        self.account = object() if subscribe and self.connection.account_id else None

    def fake_call_trader(self, method: str, *args: Any, with_account: bool = True, **kwargs: Any) -> Any:
        state["call_trader_calls"].append((method, with_account))
        return {"method": method, "with_account": with_account}

    monkeypatch.setattr(QMTGateway, "connect", fake_connect)
    monkeypatch.setattr(QMTGateway, "call_trader", fake_call_trader)
    return state


TRADE_QUERY_CLI_CASES = sorted(TRADE_QUERY_COMMANDS.items())


@pytest.mark.parametrize("command,spec", TRADE_QUERY_CLI_CASES)
def test_trade_query_command_calls_expected_method_over_cli(gateway_spy, command, spec):
    argv = [command] if command in ACCOUNT_OPTIONAL_COMMANDS else ["--account", "123456", command]

    assert main(argv) == 0

    assert gateway_spy["call_trader_calls"] == [(spec["method"], spec["with_account"])]


@pytest.mark.parametrize("command,spec", TRADE_QUERY_CLI_CASES)
def test_trade_query_command_matches_over_rpc(gateway_spy, command, spec):
    request = {"command": command.replace("-", "_")}
    if command not in ACCOUNT_OPTIONAL_COMMANDS:
        request["account"] = "123456"

    response = _handle_rpc_request(request)

    assert response["ok"] is True, response
    assert gateway_spy["call_trader_calls"] == [(spec["method"], spec["with_account"])]


@pytest.mark.parametrize("command,spec", TRADE_QUERY_CLI_CASES)
def test_trade_query_command_dash_and_underscore_rpc_aliases_agree(gateway_spy, command, spec):
    dashed = {"command": command}
    underscored = {"command": command.replace("-", "_")}
    if command not in ACCOUNT_OPTIONAL_COMMANDS:
        dashed["account"] = "123456"
        underscored["account"] = "123456"

    response_dashed = _handle_rpc_request(dashed)
    gateway_spy["call_trader_calls"].clear()
    response_underscored = _handle_rpc_request(underscored)

    assert response_dashed["ok"] is True
    assert response_underscored["ok"] is True
    assert gateway_spy["call_trader_calls"] == [(spec["method"], spec["with_account"])]


def test_orders_cancelable_only_flag_passes_true(gateway_spy, monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMTGateway, "query_orders", lambda self, cancelable_only=False: calls.append(cancelable_only) or []
    )

    assert main(["--account", "123456", "orders", "--cancelable-only"]) == 0

    assert calls == [True]


def test_orders_without_flag_defaults_to_false(gateway_spy, monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMTGateway, "query_orders", lambda self, cancelable_only=False: calls.append(cancelable_only) or []
    )

    assert main(["--account", "123456", "orders"]) == 0

    assert calls == [False]


def test_orders_cancelable_only_passes_through_rpc(gateway_spy, monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMTGateway, "query_orders", lambda self, cancelable_only=False: calls.append(cancelable_only) or []
    )

    response = _handle_rpc_request({"command": "orders", "account": "123456", "cancelable_only": True})

    assert response["ok"] is True
    assert calls == [True]


def test_ipo_data_connects_without_account_and_without_subscribe(gateway_spy):
    assert main(["ipo-data"]) == 0

    assert gateway_spy["connect_calls"] == [{"account_id": "", "subscribe": False}]
    assert gateway_spy["call_trader_calls"] == [("query_ipo_data", False)]


def test_account_infos_and_account_status_are_also_account_optional(gateway_spy):
    assert main(["account-infos"]) == 0
    assert main(["account-status"]) == 0

    assert gateway_spy["connect_calls"] == [
        {"account_id": "", "subscribe": False},
        {"account_id": "", "subscribe": False},
    ]
    assert gateway_spy["call_trader_calls"] == [
        ("query_account_infos", False),
        ("query_account_status", False),
    ]


def test_account_optional_commands_still_connect_normally_when_account_given(gateway_spy):
    assert main(["--account", "123456", "ipo-data"]) == 0

    assert gateway_spy["connect_calls"] == [{"account_id": "123456", "subscribe": False}]


@pytest.mark.parametrize(
    "command",
    sorted(set(TRADE_QUERY_COMMANDS) - ACCOUNT_OPTIONAL_COMMANDS),
)
def test_account_required_commands_still_require_account(command):
    with pytest.raises(SystemExit, match="--account is required"):
        main([command])


def test_account_optional_commands_do_not_raise_without_account():
    for command in ACCOUNT_OPTIONAL_COMMANDS:
        # Should not raise SystemExit even though --account is not registered gracefully skipped
        # here since gateway_spy is not used; a real connect would fail (no QMT install), but the
        # failure must come back as a clean error envelope (item 2), not the --account SystemExit.
        assert main([command]) == 1


# --- gateway-level: connect(subscribe=False) really skips subscribe -------------------------------


def test_gateway_connect_subscribe_false_skips_trader_subscribe_and_leaves_account_none(monkeypatch):
    calls = []

    class FakeTrader:
        def __init__(self, path, session_id):
            calls.append(("init", path, session_id))

        def start(self):
            calls.append(("start",))

        def connect(self):
            calls.append(("connect",))
            return 0

        def subscribe(self, account):
            calls.append(("subscribe", account))
            return 0

        def query_ipo_data(self):
            calls.append(("query_ipo_data",))
            return {"today": []}

    xtquant = types.ModuleType("xtquant")
    xtquant.__spec__ = importlib.machinery.ModuleSpec("xtquant", loader=None)
    xttrader = types.ModuleType("xtquant.xttrader")
    xttrader.XtQuantTrader = FakeTrader
    xttype = types.ModuleType("xtquant.xttype")
    xtconstant = types.ModuleType("xtquant.xtconstant")

    monkeypatch.setitem(sys.modules, "xtquant", xtquant)
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", xttrader)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", xttype)
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", xtconstant)

    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "", session_id=7))
    gateway.connect(subscribe=False)

    assert gateway.account is None
    assert gateway.trader is not None
    assert all(call[0] != "subscribe" for call in calls)
    assert gateway.call_trader("query_ipo_data", with_account=False) == {"today": []}
    assert calls[-1] == ("query_ipo_data",)


def test_gateway_connect_subscribe_true_with_account_id_still_subscribes(monkeypatch):
    calls = []

    class FakeTrader:
        def __init__(self, path, session_id):
            pass

        def start(self):
            pass

        def connect(self):
            return 0

        def subscribe(self, account):
            calls.append(("subscribe", account.account_id))
            return 0

    class FakeAccount:
        def __init__(self, account_id, account_type):
            self.account_id = account_id
            self.account_type = account_type

    xtquant = types.ModuleType("xtquant")
    xtquant.__spec__ = importlib.machinery.ModuleSpec("xtquant", loader=None)
    xttrader = types.ModuleType("xtquant.xttrader")
    xttrader.XtQuantTrader = FakeTrader
    xttype = types.ModuleType("xtquant.xttype")
    xttype.StockAccount = FakeAccount
    xtconstant = types.ModuleType("xtquant.xtconstant")

    monkeypatch.setitem(sys.modules, "xtquant", xtquant)
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", xttrader)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", xttype)
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", xtconstant)

    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456"))
    gateway.connect()

    assert gateway.account is not None
    assert calls == [("subscribe", "123456")]


def test_call_trader_with_account_false_does_not_require_account_set(monkeypatch):
    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", ""))
    gateway.trader = types.SimpleNamespace(query_ipo_data=lambda: {"ok": True})
    gateway.account = None

    assert gateway.call_trader("query_ipo_data", with_account=False) == {"ok": True}


def test_call_trader_with_account_true_still_requires_account_set():
    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", ""))
    gateway.trader = object()
    gateway.account = None

    with pytest.raises(RuntimeError, match="not connected"):
        gateway.call_trader("query_stock_orders", with_account=True)
