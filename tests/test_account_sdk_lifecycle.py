"""Public server boundary with the actual gateway and a fake bundled SDK."""
import io
import json
import sys
import types

import pytest

from qmtcli import cli
from qmtcli.gateway import QMTConnection, QMTGateway


@pytest.fixture
def sdk(monkeypatch):
    class Trader:
        instances = []
        fail_connect = False
        fail_subscribe = False

        def __init__(self, path, session):
            self.calls = ["init"]
            self.callback = None
            self.instances.append(self)

        def register_callback(self, callback):
            self.calls.append("register_callback")
            self.callback = callback

        def start(self):
            self.calls.append("start")

        def connect(self):
            self.calls.append("connect")
            if self.fail_connect:
                type(self).fail_connect = False
                return 1
            return 0

        def subscribe(self, account):
            self.calls.append("subscribe")
            if self.fail_subscribe:
                type(self).fail_subscribe = False
                return 1
            return 0

        def query_stock_asset(self, account):
            self.calls.append("asset")
            self.callback.on_stock_asset({"account": account.account_id, "cash": 12})
            return {"account": account.account_id, "cash": 12}

        def stop(self):
            self.calls.append("stop")
            self.callback.on_disconnected()  # Teardown callbacks must not escape EOF cleanup.

    class Account:
        def __init__(self, account, account_type):
            self.account_id = account

    monkeypatch.setattr(QMTGateway, "resolve_path", staticmethod(lambda path=None: "SYNTHETIC"))
    monkeypatch.setattr(QMTGateway, "add_sdk_path", staticmethod(lambda path=None: None))
    monkeypatch.setitem(sys.modules, "xtquant", types.ModuleType("xtquant"))
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", types.SimpleNamespace(
        XtQuantTrader=Trader, XtQuantTraderCallback=object,
    ))
    monkeypatch.setitem(sys.modules, "xtquant.xttype", types.SimpleNamespace(StockAccount=Account))
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", types.ModuleType("xtquant.xtconstant"))
    return Trader


def test_sdk_lifecycle_is_once_and_callbacks_use_real_adapter(sdk, monkeypatch, capsys):
    requests = [{"command": "account_subscribe", "account": "A"}] + [
        {"id": n, "command": "asset", "account": "A"} for n in range(40)
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(map(json.dumps, requests))))
    assert cli.main(["server"]) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    replies = [r for r in records if "ok" in r]
    events = [r for r in records if "event" in r]
    assert len(replies) == 41 and all(r["ok"] for r in replies)
    assert len(events) == 40 and all(e["type"] == "asset" and e["data"]["cash"] == 12 for e in events)
    assert len(sdk.instances) == 1
    calls = sdk.instances[0].calls
    assert calls == ["init", "register_callback", "start", "connect", "subscribe"] + ["asset"] * 40 + ["stop"]


@pytest.mark.parametrize("failure", ["fail_connect", "fail_subscribe"])
def test_failed_sdk_setup_stops_and_next_request_can_connect(sdk, monkeypatch, capsys, failure):
    setattr(sdk, failure, True)
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join([
        json.dumps({"command": "asset", "account": "A"}),
        json.dumps({"command": "asset", "account": "A"}),
    ])))
    assert cli.main(["server"]) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert not records[0]["ok"] and records[1]["ok"]
    assert len(sdk.instances) == 2 and all(t.calls.count("stop") == 1 for t in sdk.instances)


def test_sdk_async_response_deadline_does_not_wait_forever():
    gateway = QMTGateway(QMTConnection("SYNTHETIC", "A"))
    gateway.account = object()
    gateway.trader = types.SimpleNamespace(query_stock_asset_async=lambda account, callback: None)
    with pytest.raises(TimeoutError, match="response deadline exceeded"):
        gateway.query_asset(timeout=0.01)


@pytest.mark.parametrize("method,field", [
    ("query_asset", "query_stock_asset_async"),
    ("query_positions", "query_stock_positions_async"),
    ("query_orders", "query_stock_orders_async"),
    ("query_trades", "query_stock_trades_async"),
])
def test_sdk_async_response_is_returned_unchanged(method, field):
    gateway = QMTGateway(QMTConnection("SYNTHETIC", "A"))
    gateway.account = object()
    result = {"cash": 12} if method == "query_asset" else []
    gateway.trader = types.SimpleNamespace(**{
        field: lambda account, callback, **kwargs: callback(result),
    })
    assert getattr(gateway, method)(timeout=0.1) is result
