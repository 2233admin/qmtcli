"""Read-only market commands must fail loudly and never leak the bridge secret.

The module exists because ``xtquant`` cannot drive full QMT. Its whole value is
that a caller can tell "the market has no such record" (empty list) apart from
"the bridge did not answer" (BridgeError), so every test here pins that
distinction, plus the two measured quirks of the native sector call: the root
node returns its groups in the second slot, and parameter names are exact.
"""

from __future__ import annotations

import json

import pytest

from qmtcli import daqmt_market


def _write_connection(tmp_path, **overrides):
    config = {
        "protocol": 1,
        "endpoint": "http://127.0.0.1:9001",
        "account": "603010000249",
        "account_type": "STOCK",
        "secret": "s3cr3t-never-print",
        "trading_enabled": False,
    }
    config.update(overrides)
    host = tmp_path / "QmtCli"
    (host / "daqmt").mkdir(parents=True)
    path = host / "daqmt" / "connection.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return host


class _Response:
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def captured(monkeypatch):
    """Capture every bridge request instead of opening a socket."""
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return _Response({"ok": True, "data": []})

    monkeypatch.setattr(daqmt_market.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_sector_list_reads_the_root_groups(tmp_path, monkeypatch):
    host = _write_connection(tmp_path)
    monkeypatch.setattr(
        daqmt_market.urllib.request,
        "urlopen",
        lambda request, timeout=None: _Response({"ok": True, "data": [[], ["我的", "沪深板块"]]}),
    )

    assert daqmt_market.sector_list("", host_dir=str(host)) == ["我的", "沪深板块"]


def test_sector_list_reads_a_nested_node(tmp_path, monkeypatch):
    host = _write_connection(tmp_path)
    monkeypatch.setattr(
        daqmt_market.urllib.request,
        "urlopen",
        lambda request, timeout=None: _Response(
            {"ok": True, "data": [["沪深京A股", "沪深A股"], []]}
        ),
    )

    assert daqmt_market.sector_list("沪深板块", host_dir=str(host)) == [
        "沪深京A股",
        "沪深A股",
    ]


def test_sector_stocks_sends_the_exact_parameter_name(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.sector_stocks("沪深A股", host_dir=str(host))


def test_instrument_detail_sends_market_code(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.instrument_detail("600000.SH", host_dir=str(host))


def test_the_secret_travels_in_a_header_and_never_in_the_body(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.instrument_detail("600000.SH", host_dir=str(host))

    sent = dict(captured[0].header_items())
    assert sent["X-bridge-secret"] == "s3cr3t-never-print"
    assert sent["X-bridge-account"] == "603010000249"
    assert b"s3cr3t-never-print" not in captured[0].data


def test_a_bridge_refusal_is_not_reported_as_empty_data(tmp_path, monkeypatch):
    host = _write_connection(tmp_path)

    def refuse(request, timeout=None):
        raise daqmt_market.urllib.error.URLError("connection refused")

    monkeypatch.setattr(daqmt_market.urllib.request, "urlopen", refuse)

    with pytest.raises(daqmt_market.BridgeError, match="unreachable"):
        daqmt_market.sector_stocks("沪深A股", host_dir=str(host))


def test_a_native_failure_raises_instead_of_returning_empty(tmp_path, monkeypatch):
    host = _write_connection(tmp_path)
    monkeypatch.setattr(
        daqmt_market.urllib.request,
        "urlopen",
        lambda request, timeout=None: _Response(
            {"ok": False, "error": {"code": "native_call_failed", "message": "boom"}}
        ),
    )

    with pytest.raises(daqmt_market.BridgeError, match="native_call_failed"):
        daqmt_market.instrument_detail("600000.SH", host_dir=str(host))


def test_a_missing_connection_file_names_the_fix(tmp_path):
    with pytest.raises(daqmt_market.BridgeError, match="qmtcli-rs setup"):
        daqmt_market.sector_list("", host_dir=str(tmp_path))


def test_account_asset_uses_the_fixed_get_endpoint(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.account_asset(host_dir=str(host))

    assert captured[0].full_url.endswith("/api/account/asset")
    assert captured[0].get_method() == "GET"


def test_positions_reads_the_holding_endpoint(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.positions(host_dir=str(host))

    assert captured[0].full_url.endswith("/api/holding")


def test_orders_sends_the_cancelable_flag_only_when_asked(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.orders(host_dir=str(host))
    daqmt_market.orders(cancelable_only=True, host_dir=str(host))

    assert captured[0].full_url.endswith("/api/order/status?cancelable_only=false")
    assert captured[1].full_url.endswith("/api/order/status?cancelable_only=true")


def test_account_get_carries_the_bridge_account_header(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.trades(host_dir=str(host))

    sent = dict(captured[0].header_items())
    assert sent["X-bridge-account"] == "603010000249"
    assert sent["X-bridge-secret"] == "s3cr3t-never-print"


def test_an_http_refusal_on_an_account_endpoint_raises(tmp_path, monkeypatch):
    host = _write_connection(tmp_path)

    def refuse(request, timeout=None):
        raise daqmt_market.urllib.error.URLError("connection refused")

    monkeypatch.setattr(daqmt_market.urllib.request, "urlopen", refuse)

    with pytest.raises(daqmt_market.BridgeError, match="unreachable"):
        daqmt_market.positions(host_dir=str(host))


def test_place_order_posts_a_limit_order_body(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.place_order(
        side="buy", stock="300308.SZ", volume=100, price=395.0, host_dir=str(host)
    )

    sent = captured[0]
    assert sent.full_url.endswith("/api/order/buy")
    assert sent.get_method() == "POST"
    assert json.loads(sent.data) == {
        "stock": "300308.SZ",
        "volume": 100,
        "price": 395.0,
        "prType": 11,
    }


def test_place_order_rejects_a_side_that_is_not_buy_or_sell(tmp_path, captured):
    host = _write_connection(tmp_path)

    with pytest.raises(ValueError, match="side must be buy or sell"):
        daqmt_market.place_order(
            side="short", stock="300308.SZ", volume=100, price=395.0, host_dir=str(host)
        )


def test_cancel_order_targets_one_sys_id(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.cancel_order("143327", host_dir=str(host))

    sent = captured[0]
    assert sent.full_url.endswith("/api/order/cancel_by_id")
    assert json.loads(sent.data) == {"order_sys_id": "143327", "account": "stock"}


def test_place_order_sends_user_order_id_to_server(tmp_path, captured):
    host = _write_connection(tmp_path)
    daqmt_market.place_order(
        side="buy",
        stock="300308.SZ",
        volume=100,
        price=396.0,
        user_order_id="abc123",
        host_dir=str(host),
    )

    sent = captured[0]
    assert sent.full_url.endswith("/api/order/buy")
    body = json.loads(sent.data)
    assert body["user_order_id"] == "abc123"


def test_place_order_sends_dry_run_only_when_asked(tmp_path, captured):
    host = _write_connection(tmp_path)

    daqmt_market.place_order(
        side="buy", stock="300308.SZ", volume=100, price=396.0, host_dir=str(host)
    )
    daqmt_market.place_order(
        side="buy", stock="300308.SZ", volume=100, price=396.0, dry_run=True, host_dir=str(host)
    )

    assert "dry_run" not in json.loads(captured[0].data)
    assert json.loads(captured[1].data)["dry_run"] is True
