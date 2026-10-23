from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from qmtcli.cli import _handle_rpc_request
from qmtcli.gateway import QMTConnection, QMTGateway


def test_data_call_blocks_private_methods(monkeypatch):
    monkeypatch.setitem(sys.modules, "xtquant.xtdata", types.ModuleType("xtquant.xtdata"))

    with pytest.raises(ValueError, match="unknown xtdata method"):
        QMTGateway.call_data("_private")


def test_trade_call_blocks_private_methods():
    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456"))
    gateway.trader = object()
    gateway.account = object()

    with pytest.raises(ValueError, match="read-only"):
        gateway.call_trader("_private")


class _OrderingTrader:
    def __init__(self):
        self.calls = []

    def order_stock(self, *args):
        self.calls.append(("order_stock", args))
        return 1

    def cancel_order_stock(self, *args):
        self.calls.append(("cancel_order_stock", args))
        return 0

    def fund_transfer(self, *args):
        self.calls.append(("fund_transfer", args))
        return 0

    def query_stock_asset(self, account):
        return {"cash": 1}


@pytest.mark.parametrize("method", ["order_stock", "cancel_order_stock", "fund_transfer", "order_stock_async"])
def test_trade_call_refuses_every_non_query_method(method):
    """G11: an agent must not be able to place, cancel or move money through qmtcli."""
    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456"))
    trader = _OrderingTrader()
    gateway.trader = trader
    gateway.account = object()

    with pytest.raises(ValueError, match="read-only"):
        gateway.call_trader(method, "600519.SH", 23, 100)
    assert trader.calls == []


def test_trade_call_still_runs_query_methods():
    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456"))
    gateway.trader = _OrderingTrader()
    gateway.account = object()

    assert gateway.call_trader("query_stock_asset") == {"cash": 1}


@pytest.mark.parametrize("command", ["buy", "sell", "cancel"])
def test_rpc_has_no_order_commands(command):
    response = _handle_rpc_request({"command": command, "account": "1", "symbol": "600519.SH",
                                    "volume": 100, "price": 1.0, "order_id": "1"})

    assert response == {"ok": False, "error": f"unknown command: {command}"}


def test_gateway_has_no_order_methods():
    assert not hasattr(QMTGateway, "submit_order")
    assert not hasattr(QMTGateway, "cancel_order")


def test_rpc_unknown_command_returns_error_without_id():
    response = _handle_rpc_request({"command": "missing"})

    assert response["ok"] is False
    assert "unknown command" in response["error"]
    assert "id" not in response


def test_rpc_error_echoes_id():
    response = _handle_rpc_request({"id": 7, "command": "missing"})

    assert response["ok"] is False
    assert response["id"] == 7


def test_examples_are_valid_json():
    for path in [
        Path("examples/status.json"),
        Path("examples/data_call.json"),
    ]:
        assert json.loads(path.read_text(encoding="utf-8"))["command"]
