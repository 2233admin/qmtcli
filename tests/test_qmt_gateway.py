"""QMT CLI tests that do not require a real QMT install."""

from __future__ import annotations

import importlib.machinery
import io
import sys
import types

import pytest

from qmtcli.cli import main
from qmtcli.gateway import QMTConnection, QMTGateway


def test_qmt_status_without_xtquant(monkeypatch, capsys):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    assert main(["status"]) == 0

    assert '"xtquant": false' in capsys.readouterr().out


def test_qmt_connect_missing_dependency(monkeypatch):
    def missing_xtquant(name):
        if name.startswith("xtquant"):
            raise ImportError(name)
        return importlib.import_module(name)

    monkeypatch.setattr(importlib, "import_module", missing_xtquant)

    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456"))
    with pytest.raises(RuntimeError, match="xtquant is not available"):
        gateway.connect()


def test_qmt_gateway_queries_with_fake_xtquant(monkeypatch):
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
            calls.append(("subscribe", account.account_id))
            return 0

        def query_stock_asset(self, account):
            return {"account": account.account_id, "cash": 1000}

        def query_stock_positions(self, account):
            return [{"account": account.account_id, "stock_code": "600519"}]

        def query_stock_orders(self, account):
            return []

        def query_stock_trades(self, account):
            return [{"order_id": 123, "stock_code": "600519.SH"}]

        def cancel_order_stock(self, account, order_id):
            calls.append(("cancel", order_id))
            return 0

        def order_stock(self, account, symbol, order_type, volume, price_type, price, strategy, remark):
            calls.append(("order", symbol, order_type, volume, price_type, price, strategy, remark))
            return "ORDER123"

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
    xtconstant.STOCK_BUY = 23
    xtconstant.STOCK_SELL = 24
    xtconstant.FIX_PRICE = 11

    monkeypatch.setitem(sys.modules, "xtquant", xtquant)
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", xttrader)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", xttype)
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", xtconstant)

    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456", session_id=7))
    gateway.connect()

    assert gateway.query_asset()["cash"] == 1000
    assert gateway.query_positions()[0]["stock_code"] == "600519"
    assert gateway.query_orders() == []
    assert gateway.query_trades()[0]["order_id"] == 123
    assert calls[:3] == [
        ("init", gateway.connection.path, 7),
        ("start",),
        ("connect",),
    ]
    assert gateway.submit_order("600519.SH", "BUY", 100, 1500.0) == "ORDER123"
    assert calls[-1] == (
        "order",
        "600519.SH",
        23,
        100,
        11,
        1500.0,
            "qmtcli",
        "qmtcli",
    )
    assert gateway.cancel_order("123") == 0
    assert calls[-1] == ("cancel", 123)


def test_qmt_doctor_reports_read_only_sdk_support(monkeypatch, capsys):
    class FakeTrader:
        pass

    class FakeAccount:
        pass

    xtquant = types.ModuleType("xtquant")
    xttrader = types.ModuleType("xtquant.xttrader")
    xttrader.XtQuantTrader = FakeTrader
    xttype = types.ModuleType("xtquant.xttype")
    xttype.StockAccount = FakeAccount
    xtconstant = types.ModuleType("xtquant.xtconstant")
    xtconstant.STOCK_BUY = 23
    xtconstant.STOCK_SELL = 24
    xtconstant.FIX_PRICE = 11

    monkeypatch.setitem(sys.modules, "xtquant", xtquant)
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", xttrader)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", xttype)
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", xtconstant)

    assert main(["--path", "C:/missing/userdata_mini", "--account", "123456", "doctor"]) == 0

    out = capsys.readouterr().out
    assert '"mode": "trade_enabled"' in out
    assert '"XtQuantTrader": true' in out
    assert '"StockAccount": true' in out
    assert '"auto_download": false' in out


def test_qmt_doctor_reports_install_hint_when_sdk_missing(monkeypatch):
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])
    monkeypatch.setattr(importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))

    report = QMTGateway.sdk_diagnostics()

    assert report["diagnosis"]["ok"] is False
    assert report["diagnosis"]["severity"] == "error"
    assert report["diagnosis"]["auto_download"] is False
    assert "does not auto-download" in report["diagnosis"]["fix_hint"]


def test_qmt_order_validation_without_real_submit():
    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456"))
    gateway.trader = object()
    gateway.account = object()

    with pytest.raises(ValueError, match="multiple of 100"):
        gateway.submit_order("600519.SH", "BUY", 50, 100.0)


def test_qmt_rpc_status(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"command":"status"}'))

    assert main(["rpc"]) == 0

    out = capsys.readouterr().out
    assert '"ok": true' in out
    assert '"xtquant"' in out


def test_qmt_data_call(monkeypatch):
    xtdata = types.ModuleType("xtquant.xtdata")
    xtdata.get_sector_list = lambda: ["沪深A股"]
    monkeypatch.setitem(sys.modules, "xtquant.xtdata", xtdata)

    assert QMTGateway.call_data("get_sector_list") == ["沪深A股"]


def test_qmt_rpc_data_call(monkeypatch, capsys):
    xtdata = types.ModuleType("xtquant.xtdata")
    xtdata.get_stock_list_in_sector = lambda sector: ["600519.SH"] if sector == "沪深A股" else []
    monkeypatch.setitem(sys.modules, "xtquant.xtdata", xtdata)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO('{"command":"data_call","method":"get_stock_list_in_sector","args":["沪深A股"]}'),
    )

    assert main(["rpc"]) == 0

    out = capsys.readouterr().out
    assert '"ok": true' in out
    assert "600519.SH" in out


def test_qmt_server_jsonl_status(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"id":1,"command":"status"}\n'))

    assert main(["server"]) == 0

    out = capsys.readouterr().out
    assert '"id": 1' in out
    assert '"ok": true' in out
    assert '"xtquant"' in out
