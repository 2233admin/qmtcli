import io
import json
import sys

import pytest

from qmtcli import cli


@pytest.fixture
def gateway(monkeypatch):
    class FakeGateway:
        instances = []

        def __init__(self, connection):
            self.connection = connection
            self.connected = False
            self.closed = False
            self.on_event = None
            self.reads = 0
            self.instances.append(self)

        def connect(self, subscribe=True):
            self.connected = True

        def close(self):
            self.closed = True

        def query_asset(self, timeout=None):
            self.reads += 1
            return {"account": self.connection.account_id, "read": self.reads}

        def query_positions(self, timeout=None):
            return [{"stock_code": "SYNTHETIC"}]

        def query_orders(self, cancelable_only=False, timeout=None):
            return [{"order_id": 7}]

        def query_trades(self, timeout=None):
            return [{"trade_id": "T7"}]

    monkeypatch.setattr(cli, "QMTGateway", FakeGateway)
    return FakeGateway


def serve(monkeypatch, capsys, requests):
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(map(json.dumps, requests))))
    assert cli.main(["server"]) == 0
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_server_reuses_connection_but_reads_fresh(gateway, monkeypatch, capsys):
    replies = serve(monkeypatch, capsys, [
        {"id": n, "command": "asset", "account": "A"} for n in range(40)
    ])
    assert [r["data"]["read"] for r in replies] == list(range(1, 41))
    assert len(gateway.instances) == 1
    assert gateway.instances[0].closed


def test_snapshot_returns_four_sections_one_connection(gateway, monkeypatch, capsys):
    reply = serve(monkeypatch, capsys, [
        {"id": "s", "command": "account_snapshot", "account": "A"}
    ])[0]
    assert reply["ok"] and reply["id"] == "s"
    data = reply["data"]
    assert data["asset"]["account"] == "A"
    assert data["positions"][0]["stock_code"] == "SYNTHETIC"
    assert data["orders"][0]["order_id"] == 7
    assert data["trades"][0]["trade_id"] == "T7"
    assert data["meta"]["atomic"] is False
    assert data["meta"]["started_at"] <= data["meta"]["finished_at"]
    assert len(gateway.instances) == 1


def test_account_switch_closes_previous(gateway, monkeypatch, capsys):
    replies = serve(monkeypatch, capsys, [
        {"command": "asset", "account": account} for account in ["A", "A", "B"]
    ])
    assert [r["data"]["account"] for r in replies] == ["A", "A", "B"]
    assert len(gateway.instances) == 2
    assert all(g.closed for g in gateway.instances)


def test_snapshot_failure_is_error_and_next_request_reconnects(gateway, monkeypatch, capsys):
    def fail(self, timeout=None):
        raise RuntimeError("synthetic query failure")

    monkeypatch.setattr(gateway, "query_positions", fail)
    replies = serve(monkeypatch, capsys, [
        {"command": "account_snapshot", "account": "A"},
        {"command": "asset", "account": "A"},
    ])
    assert not replies[0]["ok"] and "synthetic query failure" in replies[0]["error"]
    assert replies[1]["ok"]
    assert len(gateway.instances) == 2 and all(g.closed for g in gateway.instances)


def test_events_disconnect_reconnect_and_unsubscribe(gateway, monkeypatch, capsys):
    import threading

    def inputs():
        yield json.dumps({"id": 1, "command": "account_subscribe", "account": "A"})
        old = gateway.instances[0].on_event
        old("asset", {"account_id": "OTHER_ACCOUNT", "cash": 999})
        thread = threading.Thread(target=lambda: old("asset", {"cash": 7}))
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive()
        old("disconnected", None)
        yield json.dumps({"id": 2, "command": "asset", "account": "A"})
        old("trade", {"trade_id": "STALE"})
        gateway.instances[1].on_event("position", {"stock_code": "NEW"})
        yield json.dumps({"id": 3, "command": "account_unsubscribe"})
        gateway.instances[1].on_event("trade", {"trade_id": "DISABLED"})
        yield json.dumps({"id": 4, "command": "asset", "account": "A"})

    monkeypatch.setattr(sys, "stdin", inputs())
    assert cli.main(["server"]) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    replies = [r for r in records if "ok" in r]
    events = [r for r in records if "event" in r]
    assert [r["id"] for r in replies] == [1, 2, 3, 4] and all(r["ok"] for r in replies)
    assert [e["type"] for e in events] == ["asset", "disconnected", "resync_required", "position"]
    assert events[0]["data"]["cash"] == 7 and events[-1]["data"]["stock_code"] == "NEW"
    assert events[0]["generation"] == events[1]["generation"] < events[2]["generation"]
    assert events[2]["generation"] == events[3]["generation"]
    assert [e["sequence"] for e in events] == [1, 2, 1, 2]
    assert len(gateway.instances) == 2 and all(g.closed for g in gateway.instances)


def test_native_asset_section_keeps_sdk_for_other_sections(gateway, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_native_asset", lambda request, session=None: {"native": True, "cash": 42})
    reply = serve(monkeypatch, capsys, [
        {"command": "account_snapshot", "account": "A", "asset_backend": "native"}
    ])[0]
    assert reply["ok"] and reply["data"]["asset"]["cash"] == 42
    assert reply["data"]["meta"]["asset_backend"] == "native"
    assert reply["data"]["positions"] and reply["data"]["orders"] and reply["data"]["trades"]
    assert gateway.instances[0].reads == 0


def test_snapshot_detects_disconnect_during_read(gateway, monkeypatch, capsys):
    def positions(self, timeout=None):
        self.on_event("disconnected", None)
        return []

    monkeypatch.setattr(gateway, "query_positions", positions)
    reply = serve(monkeypatch, capsys, [
        {"command": "account_snapshot", "account": "A"}
    ])[0]
    assert not reply["ok"] and "disconnected during" in reply["error"]


@pytest.mark.parametrize("method", ["query_asset", "query_positions", "query_orders", "query_trades"])
def test_missing_section_is_not_a_complete_snapshot(gateway, monkeypatch, capsys, method):
    monkeypatch.setattr(gateway, method, lambda self, timeout=None: None)
    reply = serve(monkeypatch, capsys, [{"command": "account_snapshot", "account": "A"}])[0]
    assert not reply["ok"] and "no result for" in reply["error"]


def test_empty_lists_are_valid_snapshot_results(gateway, monkeypatch, capsys):
    for method in ["query_positions", "query_orders", "query_trades"]:
        monkeypatch.setattr(gateway, method, lambda self, timeout=None: [])
    reply = serve(monkeypatch, capsys, [{"command": "account_snapshot", "account": "A"}])[0]
    assert reply["ok"]
    assert all(reply["data"][key] == [] for key in ["positions", "orders", "trades"])


def test_snapshot_discovery_and_one_shot_cleanup(gateway, monkeypatch, capsys):
    assert cli.main(["--account", "A", "account-snapshot"]) == 0
    reply = json.loads(capsys.readouterr().out)
    assert reply["ok"] and gateway.instances[0].closed
    names = {c["name"] for c in cli.AGENT_CAPABILITIES["commands"]}
    assert {"account-snapshot", "account_subscribe", "account_unsubscribe"} <= names
    assert not cli._handle_rpc_request({"command": "account_subscribe", "account": "A"})["ok"]


@pytest.mark.parametrize("field,value", [("path", "other"), ("account_type", "CREDIT")])
def test_session_identity_includes_path_and_type(gateway, monkeypatch, capsys, field, value):
    replies = serve(monkeypatch, capsys, [
        {"command": "asset", "account": "A"},
        {"command": "asset", "account": "A", field: value},
    ])
    assert all(r["ok"] for r in replies)
    assert len(gateway.instances) == 2 and all(g.closed for g in gateway.instances)


@pytest.mark.parametrize("timeout", [True, 0, -1, 61, float("inf"), "5"])
def test_snapshot_timeout_validated_before_connect(gateway, timeout):
    result = cli._handle_rpc_request({"command": "account_snapshot", "account": "A", "timeout": timeout})
    assert not result["ok"] and "snapshot timeout" in result["error"]
    assert not gateway.instances


def test_invalid_command_type_preserves_server_envelope(gateway, monkeypatch, capsys):
    replies = serve(monkeypatch, capsys, [
        {"id": 1, "command": []}, {"id": 2, "command": "asset", "account": "A"},
    ])
    assert not replies[0]["ok"] and replies[0]["id"] == 1
    assert replies[1]["ok"] and replies[1]["id"] == 2


def test_native_trade_snapshot_uses_verified_rows_and_shares_native_asset(gateway, monkeypatch, capsys):
    calls = []

    def native(request, timeout=None, session=None):
        calls.append(timeout)
        return {"asset": {"cash": 42}, "trades": [{"traded_id": "NATIVE_T1"}]}

    monkeypatch.setattr(cli, "_native_account", native)
    monkeypatch.setattr(gateway, "query_trades", lambda *a, **k: pytest.fail("SDK trade query used"))
    monkeypatch.setattr(cli, "_native_asset", lambda *a: pytest.fail("second native session opened"))
    reply = serve(monkeypatch, capsys, [{"command": "account_snapshot", "account": "A",
                                      "asset_backend": "native", "trades_backend": "native"}])[0]
    assert reply["ok"] and reply["data"]["asset"]["cash"] == 42
    assert reply["data"]["trades"][0]["traded_id"] == "NATIVE_T1"
    assert reply["data"]["meta"]["trades_backend"] == "native"
    assert len(calls) == 1


@pytest.mark.parametrize("snapshot", [False, True])
def test_jsonl_native_reuse_fresh_data_account_switch_and_eof(gateway, monkeypatch, capsys, snapshot):
    import qmtcli.native_session as native

    class Worker:
        instances = []
        generation = 1

        def __init__(self, path, account, account_type):
            self.account, self.reads, self.closed = account, 0, False
            self.instances.append(self)

        def query(self, operation, timeout):
            self.reads += 1
            asset = {"account": self.account, "read": self.reads}
            return {"asset": asset, "trades": []} if operation == "asset_trades" else asset

        def close(self):
            self.closed = True

    monkeypatch.setattr(native, "NativeSession", Worker)
    options = ({"command": "account_snapshot", "asset_backend": "native", "trades_backend": "native"}
               if snapshot else {"command": "asset", "backend": "native"})
    replies = serve(monkeypatch, capsys, [{**options, "account": a} for a in ["A", "A", "B"]])
    assert all(r["ok"] for r in replies)
    assets = [r["data"]["asset"] if snapshot else r["data"] for r in replies]
    assert assets == [{"account": "A", "read": 1}, {"account": "A", "read": 2},
                      {"account": "B", "read": 1}]
    assert len(Worker.instances) == 2 and all(w.closed for w in Worker.instances)
    if snapshot:
        assert all(r["data"]["meta"]["native_generation"] == 1 for r in replies)
        assert len(gateway.instances) == 2
    else:
        assert not gateway.instances
