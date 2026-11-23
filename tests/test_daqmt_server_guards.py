"""Orders must fail locally with a reason, not at the broker on an order that exists.

`_order_guard` runs before `passorder`. Every check here is a rejection path:
without them a fat-fingered price or size reaches the exchange and comes back
as a broker rejection on a live order.
"""

from __future__ import annotations

import importlib.util
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


def test_a_market_order_skips_the_price_band(server):
    _guard(server, price=0.0, price_type=42)


def test_a_valid_limit_order_passes(server):
    _guard(server)


def test_a_missing_contract_detail_degrades_to_the_cap_check(server):
    _guard(server, detail=None)


def test_the_cap_is_off_when_it_is_zero(server):
    _guard(server, price=396.24, volume=100000, cap=0)
