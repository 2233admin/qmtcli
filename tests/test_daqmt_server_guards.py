"""Orders must fail locally with a reason, not at the broker on an order that exists.

`_order_guard` runs before `passorder`. Every check here is a rejection path:
without them a fat-fingered price or size reaches the exchange and comes back
as a broker rejection on a live order.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_SERVER = Path(__file__).resolve().parents[1] / "bridge" / "daqmt_server.py"


def _load_server():
    """Import the in-strategy server outside QMT.

    The module subclasses `tornado.web.RequestHandler` at import time and the
    embedded QMT runtime has no pip, so a host test stubs the three names the
    import needs and nothing more.
    """
    tornado = types.ModuleType("tornado")
    web = types.ModuleType("tornado.web")
    web.RequestHandler = object
    web.HTTPError = type("HTTPError", (Exception,), {})
    iostream = types.ModuleType("tornado.iostream")
    ioloop = types.ModuleType("tornado.ioloop")
    ioloop.IOLoop = object
    tornado.web = web
    tornado.iostream = iostream
    sys.modules.setdefault("tornado", tornado)
    sys.modules.setdefault("tornado.web", web)
    sys.modules.setdefault("tornado.iostream", iostream)
    sys.modules.setdefault("tornado.ioloop", ioloop)

    spec = importlib.util.spec_from_file_location("daqmt_server_under_test", _SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def server():
    return _load_server()


class _Context:
    def __init__(self, detail):
        self._detail = detail

    def get_instrument_detail(self, stock):
        return self._detail


class _Handler:
    def __init__(self, detail):
        self._context = _Context(detail)

    def _ctx(self):
        return self._context


DETAIL = {
    "UpStopPrice": 471.84,
    "DownStopPrice": 314.56,
    "PriceTick": 0.01,
}


def _guard(server, *, detail=DETAIL, price=396.24, volume=100, price_type=11, cap=0):
    server._SDK_CONFIG = {"max_order_amount": cap}
    server._order_guard(_Handler(detail), "300308.SZ", price, volume, price_type)


def test_a_price_above_the_upper_limit_is_rejected(server):
    with pytest.raises(ValueError, match="above the upper limit"):
        _guard(server, price=471.85)


def test_a_price_below_the_lower_limit_is_rejected(server):
    with pytest.raises(ValueError, match="below the lower limit"):
        _guard(server, price=314.55)


def test_a_price_off_the_tick_grid_is_rejected(server):
    with pytest.raises(ValueError, match="tick size"):
        _guard(server, price=396.245)


def test_an_amount_above_the_cap_is_rejected(server):
    with pytest.raises(ValueError, match="exceeds max_order_amount"):
        _guard(server, price=396.24, volume=2000, cap=500000)


def test_a_volume_off_the_lot_size_is_rejected(server):
    with pytest.raises(ValueError, match="multiple of 100"):
        _guard(server, volume=150)


def test_a_market_order_skips_the_price_band(server):
    _guard(server, price=0.0, price_type=42)


def test_a_valid_limit_order_passes(server):
    _guard(server)


def test_a_missing_contract_detail_degrades_to_the_cap_check(server):
    _guard(server, detail=None)


def test_the_cap_is_off_when_it_is_zero(server):
    _guard(server, price=396.24, volume=100000, cap=0)


class _FakeOrder:
    """The fields _order_to_dict reads, so a read-back can succeed outside QMT."""

    def __init__(self, user_order_id):
        self.m_strOrderSysID = "143327"
        self.m_strRemark = user_order_id
        self.m_strInstrumentID = "300308"
        self.m_strExchangeID = "SZ"
        self.m_dLimitPrice = 396.24
        self.m_nVolumeTotalOriginal = 100
        self.m_nVolumeTraded = 0
        self.m_nVolumeTotal = 100
        self.m_nOrderStatus = 54
        self.m_strInsertDateTime = ""
        self.m_nOffsetFlag = 48


class _OrderRoute:
    """A buy handler with its JSON body, so the route can be driven without tornado."""

    DIRECTION_CODE = 23

    def __init__(self, body, *, dry_run=False):
        self.request = type("Request", (), {"body": json.dumps(body).encode()})()
        self.application = type("App", (), {"dry_run": dry_run})()
        self.replies = []

    def _ctx(self):
        return _Context(DETAIL)

    def _account(self):
        return "603010000249"

    def write_json(self, payload, status=None):
        self.replies.append((status, payload))


def _route(server, body, *, dry_run=False, accepted=True, config=None):
    route = _OrderRoute(body, dry_run=dry_run)
    server._SDK_CONFIG = config or {"max_order_amount": 0}
    key = body.get("user_order_id") or ""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            server,
            "_query_orders",
            lambda accountID, account_type: [_FakeOrder(key)] if key and accepted else [],
        )
        server._PlaceOrderMixin._do_order(route)
    return route


def test_the_buy_route_refuses_a_price_type_other_than_a_limit(server, monkeypatch):
    monkeypatch.setattr(
        server, "passorder", lambda *args: pytest.fail("passorder reached"), raising=False
    )

    route = _route(server, {"stock": "300308.SZ", "price": 0.0, "volume": 100, "prType": 5})

    assert route.replies == [
        (
            400,
            {
                "status": "error",
                "message": "dedicated endpoints accept only prType=11 (limit orders)",
            },
        )
    ]


def test_the_buy_route_rejects_an_unpriced_band_before_passorder(server, monkeypatch):
    monkeypatch.setattr(
        server, "passorder", lambda *args: pytest.fail("passorder reached"), raising=False
    )

    route = _route(server, {"stock": "300308.SZ", "price": 900.0, "volume": 100})

    assert route.replies[0][0] == 400
    assert "above the upper limit" in route.replies[0][1]["message"]


def test_a_dry_run_answers_without_reaching_passorder(server, monkeypatch):
    monkeypatch.setattr(
        server, "passorder", lambda *args: pytest.fail("passorder reached"), raising=False
    )

    route = _route(server, {"stock": "300308.SZ", "price": 396.24, "volume": 100}, dry_run=True)

    assert route.replies[0][1]["status"] == "dry_run"


def test_a_resubmitted_key_answers_duplicate_without_passorder(server, monkeypatch):
    monkeypatch.setattr(server, "passorder", lambda *args: 0, raising=False)
    server._ORDER_RESERVATIONS.clear()
    body = {"stock": "300308.SZ", "price": 396.24, "volume": 100, "user_order_id": "abc123"}

    first = _route(server, body)
    assert first.replies[0][1]["status"] == "submitted"
    assert first.replies[0][1]["broker_accepted"] is True
    assert first.replies[0][1]["order_id"] == "143327"
    second = _route(server, body)

    assert second.replies == [
        (
            200,
            {
                "status": "duplicate",
                "user_order_id": "abc123",
                "message": "order already submitted with this user_order_id",
            },
        )
    ]


def test_a_reused_key_with_other_terms_answers_conflict(server, monkeypatch):
    monkeypatch.setattr(server, "passorder", lambda *args: 0, raising=False)
    server._ORDER_RESERVATIONS.clear()

    _route(
        server, {"stock": "300308.SZ", "price": 396.24, "volume": 100, "user_order_id": "abc123"}
    )
    changed = _route(
        server, {"stock": "300308.SZ", "price": 396.24, "volume": 200, "user_order_id": "abc123"}
    )

    assert changed.replies[0][0] == 409
    assert changed.replies[0][1]["status"] == "conflict"


def test_an_order_the_broker_never_accepted_answers_unknown(server, monkeypatch):
    monkeypatch.setattr(server, "passorder", lambda *args: 0, raising=False)
    server._ORDER_RESERVATIONS.clear()
    body = {"stock": "300308.SZ", "price": 396.24, "volume": 100, "user_order_id": "ghost1"}

    route = _route(server, body, accepted=False)

    assert route.replies[0][0] == 502
    assert route.replies[0][1]["status"] == "unknown"
    assert route.replies[0][1]["retry_safe"] is False
    assert server._ORDER_RESERVATIONS["ghost1"]["status"] == "outcome_unknown"


def test_an_unknown_outcome_is_not_reported_as_a_duplicate(server, monkeypatch):
    monkeypatch.setattr(server, "passorder", lambda *args: 0, raising=False)
    server._ORDER_RESERVATIONS.clear()
    body = {"stock": "300308.SZ", "price": 396.24, "volume": 100, "user_order_id": "ghost2"}

    _route(server, body, accepted=False)
    retry = _route(server, body, accepted=False)

    assert retry.replies[0][0] == 409
    assert retry.replies[0][1]["status"] == "unknown"


@pytest.mark.parametrize("form,expected", [("full", 11), ("no_key", 10), ("minimal", 9)])
def test_each_form_sends_its_own_argument_count(server, monkeypatch, form, expected):
    seen = []
    monkeypatch.setattr(server, "passorder", lambda *args: seen.append(args) or 0, raising=False)
    server._ORDER_RESERVATIONS.clear()

    _route(
        server,
        {"stock": "300308.SZ", "price": 396.24, "volume": 100, "user_order_id": "form1"},
        config={"max_order_amount": 0, "passorder_form": form},
    )

    assert len(seen[0]) == expected


def test_the_full_form_carries_the_idempotency_key(server, monkeypatch):
    seen = []
    monkeypatch.setattr(server, "passorder", lambda *args: seen.append(args) or 0, raising=False)
    server._ORDER_RESERVATIONS.clear()

    _route(
        server,
        {"stock": "300308.SZ", "price": 396.24, "volume": 100, "user_order_id": "form2"},
        config={"max_order_amount": 0, "passorder_form": "full"},
    )

    assert seen[0][9] == "form2"


def test_a_short_form_reads_the_new_row_back_by_shape(server, monkeypatch):
    monkeypatch.setattr(server, "passorder", lambda *args: 0, raising=False)
    monkeypatch.setattr(server, "_order_ids", lambda *args: set())
    server._ORDER_RESERVATIONS.clear()

    route = _route(
        server,
        {"stock": "300308.SZ", "price": 396.24, "volume": 100, "user_order_id": "form3"},
        config={"max_order_amount": 0, "passorder_form": "minimal"},
    )

    assert route.replies[0][0] == 202
    assert route.replies[0][1]["order_id"] == "143327"


@pytest.mark.parametrize("status,expected", [(50, "已报"), (54, "已撤"), (56, "已成交")])
def test_a_verified_status_reports_its_name(server, status, expected):
    order = _FakeOrder("status-name")
    order.m_nOrderStatus = status

    assert server._order_to_dict(order)["status_name"] == expected


def test_an_unverified_status_reports_null_not_a_guess(server):
    order = _FakeOrder("status-unknown")
    order.m_nOrderStatus = 57

    record = server._order_to_dict(order)

    assert record["status"] == 57
    assert record["status_name"] is None


def test_health_reports_the_digest_of_the_running_bridge(server, monkeypatch):
    """A host compares this with the digest on disk to see whether a restart is due."""
    monkeypatch.setattr(server, "BRIDGE_SHA256", "a" * 64)

    class _Health:
        def __init__(self):
            self.application = type("App", (), {"trading_enabled": True})()
            self.payload = None

        def _ctx(self):
            return type("Ctx", (), {"get_full_tick": staticmethod(lambda: None)})()

        def write_json(self, payload, status=None):
            self.payload = payload

    handler = _Health()
    server.HealthHandler.get(handler)

    assert handler.payload["bridge_sha256"] == "a" * 64


def test_the_running_digest_comes_from_the_pinned_asset(server, tmp_path):
    """QMT gives a strategy no __file__, so the pinned asset carries the build id."""
    payload = b"print(1)\n"
    (tmp_path / "daqmt_server.py").write_bytes(payload)

    assert (
        server._build_digest({"resource_dir": str(tmp_path)}) == hashlib.sha256(payload).hexdigest()
    )
    assert server._build_digest({}) is None
    assert server._build_digest({"resource_dir": str(tmp_path / "absent")}) is None
