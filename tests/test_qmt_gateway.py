"""QMT CLI tests that do not require a real QMT install."""

from __future__ import annotations

import importlib.machinery
import importlib.metadata
import importlib.util
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

        def query_stock_orders(self, account, cancelable_only=False):
            calls.append(("query_stock_orders", cancelable_only))
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


# --- add_sdk_path: venv-first resolution, append (never prepend) fallback ------------------------


def test_add_sdk_path_does_nothing_when_xtquant_already_resolves(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    sys_path_before = list(sys.path)

    result = QMTGateway.add_sdk_path("C:/some/qmt/path")

    assert result is None
    assert sys.path == sys_path_before


def test_add_sdk_path_appends_bundled_path_when_not_resolvable(monkeypatch, tmp_path):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])
    site_packages = tmp_path / "bin.x64" / "Lib" / "site-packages"
    (site_packages / "xtquant").mkdir(parents=True)
    sentinel = "C:/already/on/sys/path"
    monkeypatch.setattr(sys, "path", [sentinel])

    result = QMTGateway.add_sdk_path(str(tmp_path))

    assert result == str(site_packages)
    # Appended after existing entries, never inserted at index 0: a venv's own numpy/pandas must
    # keep shadowing the QMT-bundled copies.
    assert sys.path == [sentinel, str(site_packages)]


def test_add_sdk_path_does_not_duplicate_path_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])
    site_packages = tmp_path / "bin.x64" / "Lib" / "site-packages"
    (site_packages / "xtquant").mkdir(parents=True)
    monkeypatch.setattr(sys, "path", [str(site_packages)])

    result = QMTGateway.add_sdk_path(str(tmp_path))

    assert result == str(site_packages)
    assert sys.path == [str(site_packages)]


# --- sdk_diagnostics: sdk_source / xtquant_version --------------------------------------------


def test_sdk_diagnostics_reports_environment_source_when_preresolved(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    report = QMTGateway.sdk_diagnostics()

    assert report["sdk_source"] == "environment"


def test_sdk_diagnostics_reports_qmt_bundled_source_when_appended(monkeypatch, tmp_path):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])
    site_packages = tmp_path / "bin.x64" / "Lib" / "site-packages"
    (site_packages / "xtquant").mkdir(parents=True)

    report = QMTGateway.sdk_diagnostics(str(tmp_path))

    assert report["sdk_source"] == "qmt_bundled"
    assert report["inputs"]["sdk_path"] == str(site_packages)


def test_sdk_diagnostics_reports_missing_source_when_nothing_found(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])

    report = QMTGateway.sdk_diagnostics("C:/nonexistent/userdata_mini")

    assert report["sdk_source"] == "missing"


def test_sdk_diagnostics_reports_xtquant_version_from_metadata(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "250516.1.1")

    report = QMTGateway.sdk_diagnostics()

    assert report["xtquant_version"] == "250516.1.1"


def test_sdk_diagnostics_falls_back_to_dunder_version_attribute(monkeypatch):
    fake_xtquant = types.ModuleType("xtquant")
    fake_xtquant.__spec__ = importlib.machinery.ModuleSpec("xtquant", loader=None)
    fake_xtquant.__version__ = "9.9.9-bundled"
    monkeypatch.setitem(sys.modules, "xtquant", fake_xtquant)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    def fake_version(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", fake_version)

    report = QMTGateway.sdk_diagnostics()

    assert report["xtquant_version"] == "9.9.9-bundled"


def test_sdk_diagnostics_xtquant_version_none_when_unavailable(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])

    def fake_version(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    monkeypatch.setattr(
        importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name))
    )

    report = QMTGateway.sdk_diagnostics()

    assert report["xtquant_version"] is None


# --- sdk_diagnostics: xtdc_available -------------------------------------------------------------


def test_sdk_diagnostics_reports_xtdc_available_true(monkeypatch):
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: object() if name in ("xtquant", "xtquant.xtdatacenter") else None,
    )
    monkeypatch.setitem(sys.modules, "xtquant", types.ModuleType("xtquant"))

    report = QMTGateway.sdk_diagnostics()

    assert report["xtdc_available"] is True


def test_sdk_diagnostics_reports_xtdc_available_false(monkeypatch):
    monkeypatch.setattr(QMTGateway, "discover_installations", lambda: [])
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: object() if name == "xtquant" else None,
    )
    monkeypatch.setitem(sys.modules, "xtquant", types.ModuleType("xtquant"))

    report = QMTGateway.sdk_diagnostics()

    assert report["xtdc_available"] is False
