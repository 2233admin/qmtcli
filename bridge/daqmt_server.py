# -*- coding: utf-8 -*-
"""DaQMT in-strategy Tornado HTTP server.

This module is NOT a standalone script. It must be loaded INSIDE the
DaQMT (??QMT) strategy runtime so that `get_trade_detail_data`,
`passorder`, `cancel`, `can_cancel_order` and `ContextInfo` are
available in this directly executed strategy. A normal Python import
does not inherit the calling strategy's injected globals.

Position/order views retain optional-field defaults. Account query errors
and missing balance fields are errors, never successful zero balances.

Only stdlib + tornado is imported; the DaQMT embedded Python has no
pip, so anything outside the bundled runtime is forbidden.
"""

import asyncio
import datetime as dt
import hmac
import json
import locale
import logging
import math
import os
import re
import sys
import threading
import uuid
from contextlib import contextmanager

import tornado.iostream
import tornado.web
from tornado.ioloop import IOLoop

_BRIDGE_SECRET = os.environ.get('DAQMT_BRIDGE_SECRET', '')
_TRADING_ENABLED = os.environ.get('DAQMT_ALLOW_TRADING') == '1'
_HTTP_LOOP = None
_HTTP_SERVER = None
_HTTP_TIMER = None
_SDK_SERVICE = None



def _read_startup_config(path=None):
    import hashlib
    from pathlib import Path
    import stat
    from urllib.parse import urlsplit

    if path is None:
        if os.name == 'nt':
            base = os.environ.get('LOCALAPPDATA')
            if not base:
                return {}
            path = Path(base) / 'QmtCli' / 'daqmt' / 'connection.json'
        else:
            base = os.environ.get('XDG_DATA_HOME')
            root = Path(base) if base else Path.home() / '.local' / 'share'
            path = root / 'qmtcli' / 'daqmt' / 'connection.json'
    path = Path(path)
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576:
        raise RuntimeError('unsafe bridge startup configuration')
    if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError('bridge startup configuration must be private')
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(config, dict):
            raise ValueError()
        allowed = {'protocol', 'endpoint', 'secret', 'account', 'account_type', 'timeout',
                   'trading_enabled', 'data_write_enabled', 'strategy_write_enabled',
                   'resource_dir', 'assets', 'init_properties', 'init_calls'}
        if set(config) - allowed or config.get('protocol') != 1:
            raise ValueError()
        endpoint = urlsplit(config['endpoint'])
        if (endpoint.scheme != 'http' or endpoint.hostname not in ('127.0.0.1', '::1') or
                endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or
                endpoint.path not in ('', '/') or not endpoint.port):
            raise ValueError()
        secret = config['secret']
        if not isinstance(secret, str) or not 1 <= len(secret) <= 8192 or not all(33 <= ord(c) <= 126 for c in secret):
            raise ValueError()
        if not isinstance(config['account'], str) or not config['account'].strip():
            raise ValueError()
        if not isinstance(config['account_type'], str) or not config['account_type']:
            raise ValueError()
        for flag in ('trading_enabled', 'data_write_enabled', 'strategy_write_enabled'):
            if type(config.get(flag)) is not bool:
                raise ValueError()
        timeout = config.get('timeout', 10)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
            raise ValueError()
        resource = Path(config['resource_dir'])
        if not resource.is_absolute() or resource.is_symlink() or resource.resolve() != path.parent.resolve():
            raise ValueError()
        assets = config['assets']
        names = {'daqmt_server.py', 'daqmt_api.py', 'daqmt_codec.py', 'daqmt_stream.py', 'catalog.json'}
        if not isinstance(assets, dict) or set(assets) - names:
            raise ValueError()
        for name, digest in assets.items():
            asset = resource / name
            if asset.is_symlink() or not isinstance(digest, str) or hashlib.sha256(asset.read_bytes()).hexdigest() != digest:
                raise ValueError()
        if not isinstance(config.get('init_properties', {}), dict) or not isinstance(config.get('init_calls', []), list):
            raise ValueError()
        config['_port'] = endpoint.port
        config['_address'] = endpoint.hostname
        return config
    except (ValueError, KeyError, TypeError, OSError, OverflowError):
        raise RuntimeError('invalid or modified bridge startup configuration') from None


_SDK_CONFIG = _read_startup_config()
if _SDK_CONFIG:
    _BRIDGE_SECRET = _SDK_CONFIG['secret']
    _TRADING_ENABLED = _SDK_CONFIG['trading_enabled']

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger('daqmt_server')


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

ACCOUNT_TYPE_MAP = {
    'stock': 'STOCK',
    'STOCK': 'STOCK',
}

# DaQMT order status codes considered "still alive" (cancelable).
# Broker eligibility is checked separately before bulk cancellation.
ACTIVE_ORDER_STATUS = (0, 1, 5)

DIRECTION_BUY = 48  # ord('0') -- DaQMT internal buy flag for stocks


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _validate_account_context(account_id, context):
    for name in ('accountID', 'accountid', 'account_id', 'strAccountID'):
        account = str(getattr(context, name, '') or '')
        if account and account != account_id:
            raise RuntimeError('DAQMT_ACCOUNT does not match the QMT strategy account')


def _account_type(account_str):
    """Map account query string to DaQMT account_type literal."""
    return ACCOUNT_TYPE_MAP.get(account_str or 'stock', 'STOCK')


def _safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(v, default=0):
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _infer_direction(o):
    """Best-effort buy/sell inference.

    DaQMT historically uses m_nDirection (48=buy, 49=sell) but some
    builds expose only m_nOffsetFlag. If neither is present we admit
    defeat and return 'unknown' rather than guessing.
    """
    if hasattr(o, 'm_nDirection'):
        return 'buy' if getattr(o, 'm_nDirection', 0) == DIRECTION_BUY else 'sell'
    if hasattr(o, 'm_nOffsetFlag'):
        return 'buy' if getattr(o, 'm_nOffsetFlag', 0) == DIRECTION_BUY else 'sell'
    return 'unknown'


def _position_to_dict(p):
    """Convert a DaQMT position object to a plain dict.

    Every field access is guarded with getattr; a missing field in some
    future DaQMT build degrades to default, never to AttributeError.
    """
    code = '{0}.{1}'.format(
        getattr(p, 'm_strInstrumentID', ''),
        getattr(p, 'm_strExchangeID', ''),
    )
    return {
        'code': code,
        'instrument_id': getattr(p, 'm_strInstrumentID', ''),
        'exchange_id': getattr(p, 'm_strExchangeID', ''),
        'instrument_name': getattr(p, 'm_strInstrumentName', ''),
        'direction': getattr(p, 'm_nDirection', 0),
        'volume': _safe_int(getattr(p, 'm_nVolume', 0)),
        'can_use_volume': _safe_int(getattr(p, 'm_nCanUseVolume', 0)),
        'frozen_volume': _safe_int(getattr(p, 'm_nFrozenVolume', 0)),
        'yesterday_volume': _safe_int(getattr(p, 'm_nYesterdayVolume', 0)),
        'on_road_volume': _safe_int(getattr(p, 'm_nOnRoadVolume', 0)),
        'open_price': _safe_float(getattr(p, 'm_dOpenPrice', 0.0)),
        'last_price': _safe_float(getattr(p, 'm_dLastPrice', 0.0)),
        'market_value': _safe_float(getattr(p, 'm_dMarketValue', 0.0)),
        'float_profit': _safe_float(getattr(p, 'm_dFloatProfit', 0.0)),
        'profit_rate': _safe_float(getattr(p, 'm_dProfitRate', 0.0)),
        'stock_holder': getattr(p, 'm_strStockHolder', ''),
        'future_trade_type': getattr(p, 'm_eFutureTradeType', 0),
        'expire_date': getattr(p, 'm_strExpireDate', ''),
    }


def _order_to_dict(o):
    """Convert a DaQMT order object to a plain dict.

    Returns the FULL set of fields downstream callers need
    (order_id/code/direction/price/volume/filled_volume/status/order_time),
    not the abbreviated 4-field shape some online examples use.
    """
    code = '{0}.{1}'.format(
        getattr(o, 'm_strInstrumentID', ''),
        getattr(o, 'm_strExchangeID', ''),
    )
    price = getattr(o, 'm_dLimitPrice', None)
    if price is None:
        price = getattr(o, 'm_dPrice', 0.0)
    volume = getattr(o, 'm_nVolumeTotalOriginal', None)
    if volume is None:
        volume = getattr(o, 'm_nVolume', 0)
    return {
        'order_id': getattr(o, 'm_strOrderSysID', ''),
        'user_order_id': getattr(o, 'm_strRemark', '') or '',
        'code': code,
        'instrument_id': getattr(o, 'm_strInstrumentID', ''),
        'exchange_id': getattr(o, 'm_strExchangeID', ''),
        'direction': _infer_direction(o),
        'price': _safe_float(price),
        'volume': _safe_int(volume),
        'filled_volume': _safe_int(getattr(o, 'm_nVolumeTraded', 0)),
        'remaining_volume': _safe_int(getattr(o, 'm_nVolumeTotal', 0)),
        'status': _safe_int(getattr(o, 'm_nOrderStatus', 0)),
        'order_time': getattr(o, 'm_strInsertDateTime', None),
    }


# ---------------------------------------------------------------------------
# DaQMT read failures propagate to HTTP errors instead of fabricated empty results.
# ---------------------------------------------------------------------------

def _query_positions(accountID, account_type):
    return globals()['get_trade_detail_data'](accountID, account_type, 'position', 'qmt') or []


def _query_account(accountID, account_type):
    rows = globals()['get_trade_detail_data'](accountID, account_type, 'account', 'qmt')
    if not rows:
        raise RuntimeError('QMT returned no account data')
    return rows


def _query_orders(accountID, account_type):
    return globals()['get_trade_detail_data'](accountID, account_type, 'order', 'qmt') or []


def _query_trades(accountID, account_type):
    return globals()['get_trade_detail_data'](accountID, account_type, 'trade', 'qmt') or []


def _trade_to_dict(t) -> dict:
    direction_raw = _safe_int(getattr(t, 'm_nOffsetFlag', getattr(t, 'm_nDirection', 0)))
    direction = 'buy' if direction_raw == 48 else 'sell'
    return {
        'trade_id':   getattr(t, 'm_strTradeID', '') or '',
        'order_id':   getattr(t, 'm_strOrderSysID', '') or '',
        'user_order_id': getattr(t, 'm_strRemark', '') or '',
        'code':       getattr(t, 'm_strInstrumentID', '') or '',
        'exchange':   getattr(t, 'm_strExchangeID', '') or '',
        'direction':  direction,
        'price':      _safe_float(getattr(t, 'm_dPrice', 0.0)),
        'volume':     _safe_int(getattr(t, 'm_nVolume', 0)),
        'amount':     _safe_float(getattr(t, 'm_dTradeAmount', 0.0)),
        'trade_time': getattr(t, 'm_strTradeTime', '') or '',
    }


# ---------------------------------------------------------------------------
# tornado handlers
# ---------------------------------------------------------------------------

class BaseHandler(tornado.web.RequestHandler):
    """Unifies JSON content-type + error response for every endpoint."""

    trading_required = True
    account_required = True

    def set_default_headers(self):
        self.set_header('Content-Type', 'application/json; charset=utf-8')

    def write_json(self, obj, status=None):
        if status is not None:
            self.set_status(status)
        # ensure_ascii=False so ???? names survive; UTF-8 via header above.
        self.write(json.dumps(obj, ensure_ascii=False, default=str))

    def write_error(self, status_code, **kwargs):
        self.set_header('Content-Type', 'application/json; charset=utf-8')
        self.write(json.dumps({
            'status': 'error',
            'code': status_code,
            'message': self._reason,
        }, ensure_ascii=False))

    def prepare(self):
        supplied = self.request.headers.get('X-Bridge-Secret', '')
        if not _BRIDGE_SECRET or not hmac.compare_digest(
                supplied.encode('utf-8'), _BRIDGE_SECRET.encode('utf-8')):
            self.write_json({'status': 'error', 'message': 'forbidden'}, status=403)
            self.finish()
            return
        requested_account = self.request.headers.get('X-Bridge-Account')
        if self.account_required and requested_account is not None and requested_account != self.application.accountID:
            raise tornado.web.HTTPError(400, reason='requested account does not match bridge account')
        if self.request.method == 'POST' and self.trading_required and not self.application.trading_enabled:
            self.write_json({'status': 'error', 'message': 'trading is disabled'}, status=403)
            self.finish()
            return
        if self.application.stopping:
            raise tornado.web.HTTPError(503, reason='bridge is stopping')
        # Keep one verified context for the request across later scheduler turns.
        self._request_context = self.application.ContextInfo
        if self.account_required:
            _validate_account_context(self._account(), self._request_context)

    def _ctx(self):
        return self._request_context

    def _account(self):
        return self.application.accountID


class HoldingHandler(BaseHandler):
    """GET /api/holding?account=stock -> dict keyed by code."""

    def get(self):
        account_type = _account_type(self.get_argument('account', 'stock'))
        positions = _query_positions(self._account(), account_type)
        out = {}
        for p in positions:
            try:
                d = _position_to_dict(p)
                out[d['code']] = d
            except Exception as exc:
                logger.error('position serialization failed: %s', exc)
        self.write_json(out)


def _balance_value(account, field):
    value = float(getattr(account, field))
    if not math.isfinite(value):
        raise ValueError('QMT account field is not finite: ' + field)
    return value


def _money_value(account_id, account_type, field):
    return _balance_value(_query_account(account_id, account_type)[0], field)


class TotalMoneyHandler(BaseHandler):
    """GET /api/money/total?account=stock -> {total_money}."""

    def get(self):
        kind = _account_type(self.get_argument('account', 'stock'))
        self.write_json({'total_money': _money_value(self._account(), kind, 'm_dBalance')})


class AvailableMoneyHandler(BaseHandler):
    """GET /api/money/available?account=stock -> {available_money}."""

    def get(self):
        kind = _account_type(self.get_argument('account', 'stock'))
        self.write_json({'available_money': _money_value(self._account(), kind, 'm_dAvailable')})


class HealthHandler(BaseHandler):
    def get(self):
        methods = ('get_full_tick', 'get_market_data_ex', 'subscribe_quote',
                   'subscribe_whole_quote', 'get_all_subscription', 'unsubscribe_quote')
        self.write_json({'backend': 'daqmt', 'bridge_running': True,
                         'trading_enabled': self.application.trading_enabled,
                         'capability_observation': 'callable-only; not native liveness',
                         'capabilities': {name: callable(getattr(self._ctx(), name, None)) for name in methods}})


class AssetHandler(BaseHandler):
    def get(self):
        account = _query_account(self._account(), 'STOCK')[0]
        self.write_json({'account_id': self._account(), 'cash': _balance_value(account, 'm_dAvailable'),
                         'total_asset': _balance_value(account, 'm_dBalance')})


class OrderStatusHandler(BaseHandler):
    """GET /api/order/status?account=stock -> {orders:[...]}."""

    def get(self):
        account_type = _account_type(self.get_argument('account', 'stock'))
        cancelable = self.get_argument('cancelable_only', 'false')
        if cancelable not in ('true', 'false'):
            raise tornado.web.HTTPError(400, reason='cancelable_only must be true or false')
        eligibility = globals().get('can_cancel_order')
        if cancelable == 'true' and not callable(eligibility):
            raise tornado.web.HTTPError(503, reason='QMT can_cancel_order is unavailable')
        orders = _query_orders(self._account(), account_type)
        out = []
        for order in orders:
            try:
                record = _order_to_dict(order)
            except Exception as exc:
                logger.error('order serialization failed: %s', exc)
                continue
            if cancelable == 'true':
                try:
                    if not record['order_id'] or not eligibility(record['order_id'], self._account(), account_type):
                        continue
                except Exception:
                    logger.exception('QMT order eligibility query failed')
                    raise tornado.web.HTTPError(502, reason='QMT order eligibility query failed')
            out.append(record)
        self.write_json({'orders': out})


class TradeStatusHandler(BaseHandler):
    """GET /api/trade/status?account=stock -> {trades: [...]}"""

    def get(self):
        account_type = _account_type(self.get_argument('account', 'stock'))
        trades = _query_trades(self._account(), account_type)
        out = []
        for t in trades:
            try:
                out.append(_trade_to_dict(t))
            except Exception as exc:
                logger.error('trade serialization failed: %s', exc)
        self.write_json({'trades': out})


def _parse_json_body(handler):
    raw = handler.request.body or b'{}'
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode('gbk')
    body = json.loads(text)
    if not isinstance(body, dict):
        raise ValueError('JSON body must be an object')
    return body


def _order_intent(body):
    stock, volume = body.get('stock'), body.get('volume')
    if not isinstance(stock, str) or not re.fullmatch(r'[0-9]{6}\.(SH|SZ|BJ)', stock):
        raise ValueError('stock must be a six-digit .SH, .SZ or .BJ symbol')
    price_type = body.get('prType', 11)
    if type(price_type) is not int or not (0 <= price_type <= 14 or 42 <= price_type <= 49):
        raise ValueError('prType is not a documented stock quote mode')
    exchange = stock[-2:]
    if (price_type in (42, 43) and exchange == 'SZ') or (
            price_type in (46, 47, 48) and exchange != 'SZ'):
        raise ValueError('prType is not supported on this exchange')
    price = body.get('price', 0.0)
    if type(price) not in (int, float):
        raise ValueError('price must be a finite JSON number')
    try:
        price = float(price)
    except OverflowError:
        raise ValueError('price must be finite')
    if not math.isfinite(price):
        raise ValueError('price must be finite')
    if price_type == 11 and price <= 0:
        raise ValueError('specified-price orders require a positive price')
    # SH/BJ market orders use price as protection; zero means the exchange price limit.
    if exchange in ('SH', 'BJ') and price_type in (42, 43, 44, 45) and not 0 <= price <= 9999:
        raise ValueError('market-order protection price must be in [0, 9999]')
    if type(volume) is not int or volume <= 0:
        raise ValueError('volume must be a positive integer number of shares')
    user_order_id = body['user_order_id'] if 'user_order_id' in body else uuid.uuid4().hex
    if not isinstance(user_order_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', user_order_id):
        raise ValueError('user_order_id must contain 1-32 ASCII letters, digits, _ or -')
    return stock, price, volume, price_type, user_order_id


class _PlaceOrderMixin(object):
    """Submit one validated intent; a local return is not a broker acknowledgement."""

    DIRECTION_CODE = None  # 23=buy, 24=sell

    def _do_order(self):
        try:
            stock, price, volume, price_type, user_order_id = _order_intent(_parse_json_body(self))
        except (ValueError, TypeError, UnicodeError) as exc:
            self.write_json({'status': 'error', 'message': str(exc)}, status=400)
            return
        try:
            # The documented expanded form puts userOrderId before ContextInfo.
            native_result = globals()['passorder'](
                self.DIRECTION_CODE, 1101, self._account(), stock,
                price_type, price, volume, 'qmt', 2, user_order_id, self._ctx(),
            )
            if isinstance(native_result, int) and native_result < 0:
                raise RuntimeError('passorder returned failure code {0}'.format(native_result))
        except Exception as exc:
            logger.exception('passorder raised %s; outcome unknown, do not retry', type(exc).__name__)
            self.write_json({
                'status': 'unknown', 'message': '{0}: {1!r}'.format(type(exc).__name__, exc),
                'user_order_id': user_order_id, 'broker_accepted': None, 'retry_safe': False,
            }, status=502)
            return
        self.write_json({
            'status': 'submitted', 'user_order_id': user_order_id, 'broker_accepted': None,
        }, status=202)


class BuyHandler(BaseHandler, _PlaceOrderMixin):
    """POST /api/order/buy."""
    DIRECTION_CODE = 23

    def post(self):
        self._do_order()


class SellHandler(BaseHandler, _PlaceOrderMixin):
    """POST /api/order/sell."""
    DIRECTION_CODE = 24

    def post(self):
        self._do_order()


class CancelAllHandler(BaseHandler):
    """POST /api/order/cancel_all -> cancel every order whose status is in
    ACTIVE_ORDER_STATUS. Returns the list of order_sys_ids we attempted
    to cancel (whether the broker accepted them or not is async)."""

    def post(self):
        account_type = _account_type(self.get_argument('account', 'stock'))
        orders = _query_orders(self._account(), account_type)
        canceled = []
        for o in orders:
            status = _safe_int(getattr(o, 'm_nOrderStatus', 0))
            if status not in ACTIVE_ORDER_STATUS:
                continue
            sys_id = getattr(o, 'm_strOrderSysID', '')
            if not sys_id:
                continue
            try:
                if globals()['can_cancel_order'](sys_id, self._account(), account_type):
                    globals()['cancel'](sys_id, self._account(), account_type, self._ctx())
                    canceled.append(sys_id)
            except Exception as exc:
                logger.error('cancel(%s) failed: %s', sys_id, exc)
        self.write_json({'status': 'success', 'canceled_orders': canceled})


class CancelOrderHandler(BaseHandler):
    """POST /api/order/cancel_order.

    Body: {"stock": "000001.SZ", "volume": 1000, "account": "stock"}

    Matching code and remaining volume can cancel several orders. Use
    /api/order/cancel_by_id with an observed system order ID for precise targeting.
    """

    def post(self):
        try:
            body = _parse_json_body(self)
        except Exception:
            self.write_json({'status': 'error', 'message': 'invalid json'}, status=400)
            return

        stock = body.get('stock')
        volume = body.get('volume')
        account_type = _account_type(body.get('account', 'stock'))

        if not isinstance(stock, str) or not stock or type(volume) is not int or volume <= 0:
            self.write_json(
                {'status': 'error', 'message': 'stock + volume required'},
                status=400,
            )
            return

        orders = _query_orders(self._account(), account_type)
        canceled_sys_ids = []
        for o in orders:
            status = _safe_int(getattr(o, 'm_nOrderStatus', 0))
            if status not in ACTIVE_ORDER_STATUS:
                continue
            code = '{0}.{1}'.format(
                getattr(o, 'm_strInstrumentID', ''),
                getattr(o, 'm_strExchangeID', ''),
            )
            if code != stock:
                continue
            remaining = _safe_int(getattr(o, 'm_nVolumeTotal', 0))
            if remaining != volume:
                continue
            sys_id = getattr(o, 'm_strOrderSysID', '')
            if not sys_id:
                continue
            try:
                if globals()['can_cancel_order'](sys_id, self._account(), account_type):
                    globals()['cancel'](sys_id, self._account(), account_type, self._ctx())
                    canceled_sys_ids.append(sys_id)
            except Exception as exc:
                logger.error('cancel(%s) failed: %s', sys_id, exc)

        self.write_json({'status': 'success', 'canceled_sys_ids': canceled_sys_ids})


class CancelByIdHandler(BaseHandler):
    """POST /api/order/cancel_by_id  Body: {"order_sys_id": "xxxx", "account": "stock"}

    Cancels a specific order by its m_strOrderSysID. Unlike cancel_order (which
    matches by code+remaining_volume), this is precise -- no partial-fill ambiguity.
    """

    def post(self):
        try:
            body = _parse_json_body(self)
        except Exception:
            self.set_status(400)
            self.write_json({'error': 'invalid json body'})
            return

        order_sys_id = body.get('order_sys_id', '')
        if not isinstance(order_sys_id, str) or not order_sys_id.strip():
            self.set_status(400)
            self.write_json({'error': 'order_sys_id required'})
            return

        account_type = _account_type(body.get('account', self.get_argument('account', 'stock')))
        try:
            globals()['cancel'](order_sys_id, self._account(), account_type, self._ctx())
            self.write_json({'status': 'success', 'order_sys_id': order_sys_id})
        except Exception as exc:
            logger.error('cancel_by_id(%s) failed: %s', order_sys_id, exc)
            self.set_status(500)
            self.write_json({'error': str(exc), 'order_sys_id': order_sys_id})


# ---------------------------------------------------------------------------
# market data
# ---------------------------------------------------------------------------

def _market_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _market_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_market_value(item) for item in value]
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if hasattr(value, 'columns') and hasattr(value, 'index') and hasattr(value, 'to_json'):
        return json.loads(value.to_json(orient='split', date_format='iso'))
    if hasattr(value, 'tolist'):
        return _market_value(value.tolist())
    if hasattr(value, 'item'):
        return _market_value(value.item())
    raise TypeError('Unsupported market value: ' + type(value).__name__)


def _market_json(value):
    return json.dumps(_market_value(value), ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def _track_market_task(app, task):
    app.market_tasks.add(task)
    task.add_done_callback(app.market_tasks.discard)


class MarketHandler(BaseHandler):
    def write_json(self, payload, status=200):
        encoded = _market_json(payload)
        self.set_status(status)
        self.set_header('Content-Type', 'application/json; charset=utf-8')
        self.write(encoded)

    def write_error(self, status_code, **kwargs):
        exc = kwargs.get('exc_info', (None, None, None))[1]
        self.write_json({'status': 'error', 'message': getattr(exc, 'reason', None)
                         or 'market request failed'}, status=status_code)

    def _symbol(self):
        symbol = self.get_argument('symbol', '').strip()
        if len(symbol) > 64 or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z][A-Za-z0-9]*', symbol):
            raise tornado.web.HTTPError(400, reason='symbol must be a QMT code.exchange')
        return symbol

    def _period(self, default):
        period = self.get_argument('period', default)
        if not re.fullmatch(r'tick|[1-9][0-9]{0,3}(?:ms|s|m|h|d|w|mon|q|hy|y)', period):
            raise tornado.web.HTTPError(400, reason='invalid explicit market period')
        return period

    def _method(self, name):
        method = getattr(self._ctx(), name, None)
        if not callable(method):
            raise tornado.web.HTTPError(503, reason='QMT market API unavailable: ' + name)
        return method


def _market_selectors(handler, name, allow_markets=False):
    text = handler.get_argument(name, '')
    codes = text.split(',')
    pattern = r'[A-Za-z0-9_-]+\.[A-Za-z][A-Za-z0-9]*'
    if allow_markets:
        pattern = r'(?:' + pattern + r'|[A-Za-z][A-Za-z0-9]*)'
    if not text or any(len(code) > 64 or not re.fullmatch(pattern, code) for code in codes):
        raise tornado.web.HTTPError(400, reason=name + ' requires native market or qualified symbol codes')
    return codes


class MarketTickHandler(MarketHandler):
    def get(self):
        batch = 'symbols' in self.request.arguments
        symbols = _market_selectors(self, 'symbols', allow_markets=True) if batch else [self._symbol()]
        get_tick = self._method('get_full_tick')
        try:
            data = get_tick(symbols)
        except Exception:
            logger.exception('QMT full tick query failed')
            raise tornado.web.HTTPError(502, reason='QMT full tick query failed')
        if not isinstance(data, dict):
            raise tornado.web.HTTPError(502, reason='QMT returned an invalid full tick result')
        if not data or any('.' in symbol and symbol not in data for symbol in symbols):
            raise tornado.web.HTTPError(503, reason='QMT has no cached tick for a requested symbol')
        if any(not isinstance(tick, dict) for tick in data.values()):
            raise tornado.web.HTTPError(502, reason='QMT returned an invalid tick')
        try:
            self.write(_market_json({'ticks': data} if batch else {'symbol': symbols[0], 'tick': data[symbols[0]]}))
        except (TypeError, ValueError):
            raise tornado.web.HTTPError(502, reason='QMT returned an invalid full tick result')


class MarketBarsHandler(MarketHandler):
    def get(self):
        batch = 'symbols' in self.request.arguments
        symbols = _market_selectors(self, 'symbols') if batch else [self._symbol()]
        period = self._period('1d')
        count_text = self.get_argument('count', '100')
        if count_text != '-1' and (not re.fullmatch(r'[0-9]{1,4}', count_text) or not 1 <= int(count_text) <= 2000):
            raise tornado.web.HTTPError(400, reason='count must be -1 or an integer from 1 to 2000')
        dates = [self.get_argument(name, '') for name in ('start', 'end')]
        for date in dates:
            if date:
                try:
                    if not re.fullmatch(r'[0-9]{8}|[0-9]{14}', date):
                        raise ValueError('invalid date format')
                    dt.datetime.strptime(date, '%Y%m%d' if len(date) == 8 else '%Y%m%d%H%M%S')
                except ValueError:
                    raise tornado.web.HTTPError(400, reason='dates must use YYYYMMDD or YYYYMMDDhhmmss')
        if dates[0] and dates[1] and (
                dates[0][:8] > dates[1][:8] or
                (len(dates[0]) == len(dates[1]) and dates[0] > dates[1])):
            raise tornado.web.HTTPError(400, reason='start must not be after end')
        fields_text = self.get_argument('fields', '')
        fields = fields_text.split(',') if fields_text else []
        if any(len(field) > 64 or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', field) for field in fields):
            raise tornado.web.HTTPError(400, reason='fields must be native field identifiers')
        dividend = self.get_argument('dividend_type', 'none')
        if dividend not in ('none', 'front', 'back', 'front_ratio', 'back_ratio'):
            raise tornado.web.HTTPError(400, reason='invalid dividend_type')
        fill = self.get_argument('fill_data', 'false')
        if fill not in ('true', 'false'):
            raise tornado.web.HTTPError(400, reason='fill_data must be true or false')
        query = self._method('get_market_data_ex')
        try:
            data = query(fields, symbols, period=period, start_time=dates[0], end_time=dates[1],
                         count=int(count_text), dividend_type=dividend, fill_data=fill == 'true', subscribe=False)
            if not isinstance(data, dict):
                raise ValueError('invalid market data result')
            if any(symbol not in data for symbol in symbols):
                raise tornado.web.HTTPError(503, reason='QMT has no local bars for a requested symbol')
            frames = {}
            for symbol in symbols:
                frame = data.get(symbol)
                if not hasattr(frame, 'columns') or not hasattr(frame, 'index') or not callable(getattr(frame, 'to_json', None)):
                    raise ValueError('missing or invalid market data frame')
                frames[symbol] = _market_value(frame)
            payload = {'period': period, 'bars': frames} if batch else {
                'symbol': symbols[0], 'period': period, 'bars': frames[symbols[0]]}
            self.write(_market_json(payload))
        except tornado.web.HTTPError:
            raise
        except Exception:
            logger.exception('QMT market bars query failed')
            raise tornado.web.HTTPError(502, reason='QMT market bars query failed')


def _check_quote_ownership(app, native_id, claimant):
    legacy = [stream for stream in app.market_streams
              if stream._subscription_id == native_id]
    sdk = [stream for stream in app.sdk.streams.values()
           if stream.native_domain == 'quote' and stream.native_id == native_id]
    if claimant not in legacy and claimant not in sdk:
        (legacy if hasattr(claimant, '_subscription_id') else sdk).append(claimant)
    if len(legacy) + len(sdk) <= 1:
        return True
    # Clear every ambiguous identity before any retirement can reach the SDK.
    for stream in legacy:
        stream._subscription_id = None
    for stream in sdk:
        stream.native_id = None
    app.market_cleanup_error = RuntimeError('native subscription identity is ambiguous')
    for stream in legacy + sdk:
        stream.retire('native subscription identity is ambiguous')
    return False


class MarketStreamHandler(MarketHandler):
    def initialize(self):
        self._quote_lock = threading.Lock()
        self._closed = True
        self._ready = False
        self._delivery_scheduled = False
        self._latest_quote = None
        self._subscription_id = None
        self._subscription_context = None
        self._stream_done = None
        self._quote_loop = None
        self._stream_id = uuid.uuid4().hex
        self._stream_details = {}

    def _register(self):
        symbol = self._symbol()
        period = self._period('tick')
        self._stream_details = {'kind': 'quote', 'symbol': symbol, 'period': period, 'mode': 'latest'}
        return self._method('subscribe_quote')(
            symbol, period=period, dividend_type='none', result_type='list', callback=self._on_quote)

    def description(self):
        return dict(self._stream_details, subscription_id=self._subscription_id, stream_id=self._stream_id)

    async def get(self):
        self._method('unsubscribe_quote')
        self._quote_loop = IOLoop.current()
        self._stream_done = self._quote_loop.asyncio_loop.create_future()
        current_task = getattr(asyncio, 'current_task', None)
        task = current_task() if current_task else asyncio.Task.current_task()
        _track_market_task(self.application, task)
        self._subscription_context = self._ctx()
        self._closed = False
        self.application.market_streams.add(self)
        try:
            # Native registration may reenter Stop before returning its subscription ID.
            subscription_id = self._register()
            if isinstance(subscription_id, bool) or not isinstance(subscription_id, int) or subscription_id <= 0:
                raise tornado.web.HTTPError(502, reason='QMT did not return a positive subscription ID')
            self._subscription_id = subscription_id
            if not _check_quote_ownership(self.application, subscription_id, self):
                raise tornado.web.HTTPError(502, reason='ambiguous native subscription ID; cleanup uncertain')
            if self._closed or self.application.stopping:
                raise tornado.web.HTTPError(503, reason='bridge stopped during subscription registration')
            self.set_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.set_header('Cache-Control', 'no-store')
            self.write('event: subscribed\ndata: ' + _market_json(self.description()) + '\n\n')
            await self.flush()
            # Do not let an immediate native quote overtake subscription metadata.
            with self._quote_lock:
                self._ready = not self._closed
                self._queue_delivery_locked()
            await self._stream_done
        except tornado.iostream.StreamClosedError:
            pass
        except tornado.web.HTTPError:
            raise
        except Exception:
            logger.exception('QMT market subscription failed')
            raise tornado.web.HTTPError(502, reason='QMT market subscription failed')
        finally:
            self.retire()

    def _queue_delivery_locked(self):
        if self._ready and not self._closed and self._latest_quote is not None and not self._delivery_scheduled:
            self._delivery_scheduled = True
            self._quote_loop.add_callback(self._start_delivery)

    def _on_quote(self, data):
        # Freeze native-owned payloads before publishing them to the owner-loop handoff.
        with self._quote_lock:
            if self._closed:
                return
        try:
            if not isinstance(data, dict) or any(
                    not isinstance(code, str) or len(code) > 64 or
                    not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z][A-Za-z0-9]*', code) or
                    not isinstance(value, dict) for code, value in data.items()):
                raise ValueError('invalid symbol-keyed quote batch')
            if not data:
                return
            quote = ('quote', {code: _market_json(value) for code, value in data.items()})
        except Exception:
            logger.exception('QMT returned an invalid market callback')
            quote = ('error', _market_json({'error': 'invalid QMT market callback'}))
        with self._quote_lock:
            if not self._closed:
                if self._latest_quote is None or self._latest_quote[0] != 'error':
                    if quote[0] == 'quote' and self._latest_quote is not None:
                        self._latest_quote[1].update(quote[1])
                    else:
                        self._latest_quote = quote
                self._queue_delivery_locked()

    def _start_delivery(self):
        if self._closed:
            return
        task = asyncio.ensure_future(self._deliver_quote())
        _track_market_task(self.application, task)
        return task

    async def _deliver_quote(self):
        with self._quote_lock:
            quote, self._latest_quote = self._latest_quote, None
        try:
            if self._closed or quote is None:
                return
            _validate_account_context(self._account(), self.application.ContextInfo)
            if quote[0] == 'quote':
                payload = '{' + ','.join(json.dumps(code) + ':' + value
                                         for code, value in quote[1].items()) + '}'
            else:
                payload = quote[1]
            self.write('event: ' + quote[0] + '\ndata: ' + payload + '\n\n')
            await self.flush()
            if quote[0] == 'error':
                self.retire()
        except tornado.iostream.StreamClosedError:
            self.retire()
        except Exception:
            logger.exception('QMT market stream failed')
            self.retire('market stream failed')
        finally:
            with self._quote_lock:
                self._delivery_scheduled = False
                self._queue_delivery_locked()

    def retire(self, reason=None):
        with self._quote_lock:
            was_open = not self._closed
            self._closed = True
            self._ready = False
            self._latest_quote = None
        subscription_id = self._subscription_id
        if subscription_id is not None:
            if not _check_quote_ownership(self.application, subscription_id, self):
                subscription_id = None
        self._subscription_id = None
        self.application.market_streams.discard(self)
        if reason and was_open:
            try:
                self.write('event: error\ndata: ' + _market_json({'error': reason}) + '\n\n')
            except tornado.iostream.StreamClosedError:
                pass
        if self._stream_done is not None and not self._stream_done.done():
            self._stream_done.set_result(None)
        if subscription_id is not None:
            try:
                self._subscription_context.unsubscribe_quote(subscription_id)
            except Exception as exc:
                logger.exception('QMT market unsubscribe failed for ID %s', subscription_id)
                if self.application.market_cleanup_error is None:
                    self.application.market_cleanup_error = exc

    def on_connection_close(self):
        self.retire()


class WholeMarketStreamHandler(MarketStreamHandler):
    def _register(self):
        codes = _market_selectors(self, 'codes', allow_markets=True)
        if self.get_argument('period', 'tick') != 'tick':
            raise tornado.web.HTTPError(400, reason='whole quote only supports tick')
        self._stream_details = {'kind': 'whole', 'codes': list(codes), 'period': 'tick', 'mode': 'latest'}
        return self._method('subscribe_whole_quote')(codes, callback=self._on_quote)


def _subscription_snapshot(app, context):
    getter = getattr(context, 'get_all_subscription', None)
    if not callable(getter):
        raise tornado.web.HTTPError(503, reason='QMT subscription inventory unavailable')
    try:
        entries = getter()
        if not isinstance(entries, dict):
            raise ValueError('QMT did not return a registration map')
        entries = _market_value(entries)
    except Exception:
        logger.exception('QMT subscription inventory failed')
        raise tornado.web.HTTPError(502, reason='QMT subscription inventory failed')
    streams = [stream.description() for stream in app.market_streams
               if stream._subscription_id is not None and not stream._closed]
    streams += [stream.description() for stream in app.sdk.streams.values()
                if not stream.closed]
    return {'sdk_context_registrations': {
                'scope': 'current-strategy-context', 'source': 'ContextInfo.get_all_subscription',
                'native_liveness_verified': False, 'entries': entries},
            'bridge_open_streams': sorted(streams, key=lambda item: item['stream_id']),
            'cleanup_failed': app.market_cleanup_error is not None}


class MarketSubscriptionsHandler(MarketHandler):
    def get(self):
        self.write(_market_json(_subscription_snapshot(self.application, self._ctx())))


class MarketUnsubscribeHandler(MarketHandler):
    trading_required = False

    def post(self):
        try:
            body = _parse_json_body(self)
            subscription_id, stream_id = body.get('subscription_id'), body.get('stream_id')
            if isinstance(subscription_id, bool) or not isinstance(subscription_id, int) or subscription_id <= 0:
                raise ValueError('positive subscription_id required')
            if not isinstance(stream_id, str) or not re.fullmatch(r'[0-9a-f]{32}', stream_id):
                raise ValueError('stream_id from subscription metadata required')
        except (ValueError, UnicodeDecodeError) as exc:
            raise tornado.web.HTTPError(400, reason=str(exc))
        owners = [stream for stream in self.application.market_streams
                  if stream._subscription_id == subscription_id and not stream._closed]
        if len(owners) > 1:
            raise tornado.web.HTTPError(409, reason='ambiguous native subscription ownership')
        if not owners or owners[0]._stream_id != stream_id:
            raise tornado.web.HTTPError(404, reason='no matching bridge-owned stream')
        owners[0].retire()
        if self.application.market_cleanup_error is not None:
            raise tornado.web.HTTPError(502, reason='native market cleanup is uncertain')
        self.write_json({'status': 'retired', 'subscription_id': subscription_id, 'stream_id': stream_id,
                         'native_liveness_verified': False})


# ---------------------------------------------------------------------------
# app factory + entrypoint
# ---------------------------------------------------------------------------

class DebugContextHandler(BaseHandler):
    """Authenticated runtime diagnostics, without dumping account/context attributes."""

    def get(self):
        names = ('get_trade_detail_data', 'passorder', 'cancel', 'can_cancel_order')
        self.write_json({
            'runtime': 'full-qmt', 'python': sys.version,
            'account_suffix': str(self._account())[-4:],
            'trading_enabled': self.application.trading_enabled,
            'api': {name: callable(globals().get(name)) for name in names},
            'passorder_doc': getattr(globals().get('passorder'), '__doc__', '') or '',
        })



def _load_sdk_assets():
    """Load only the bridge's own colocated assets, never a request-selected path."""
    import importlib.util
    from pathlib import Path

    root = (Path(_SDK_CONFIG['resource_dir']) if _SDK_CONFIG else
            Path(__file__).resolve().parent)
    modules = {}
    for name in ('daqmt_codec', 'daqmt_api', 'daqmt_stream'):
        spec = importlib.util.spec_from_file_location(name, str(root / (name + '.py')))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    catalog_path = root / 'catalog.json'
    if not catalog_path.is_file():
        catalog_path = root.parent / 'api' / 'catalog.json'
    catalog = modules['daqmt_api'].json_loads(catalog_path.read_text(encoding='utf-8'))
    if catalog.get('protocol') != 1:
        raise RuntimeError('unsupported bridge catalog protocol')
    return modules['daqmt_api'], modules['daqmt_codec'], modules['daqmt_stream'], catalog

def make_app():
    if not _BRIDGE_SECRET:
        raise RuntimeError('DAQMT_BRIDGE_SECRET is required')
    sdk_api, sdk_codec, sdk_stream, catalog = _load_sdk_assets()
    app = tornado.web.Application([
        (r'/api/market/tick', MarketTickHandler),
        (r'/api/market/bars', MarketBarsHandler),
        (r'/api/market/stream', MarketStreamHandler),
        (r'/api/market/whole-stream', WholeMarketStreamHandler),
        (r'/api/market/subscriptions', MarketSubscriptionsHandler),
        (r'/api/market/unsubscribe', MarketUnsubscribeHandler),
        (r'/api/health', HealthHandler),
        (r'/api/account/asset', AssetHandler),
        (r'/api/holding', HoldingHandler),
        (r'/api/money/total', TotalMoneyHandler),
        (r'/api/money/available', AvailableMoneyHandler),
        (r'/api/order/status', OrderStatusHandler),
        (r'/api/order/buy', BuyHandler),
        (r'/api/order/sell', SellHandler),
        (r'/api/order/cancel_all', CancelAllHandler),
        (r'/api/order/cancel_order', CancelOrderHandler),
        (r'/api/order/cancel_by_id', CancelByIdHandler),
        (r'/api/trade/status', TradeStatusHandler),
        (r'/api/debug/context', DebugContextHandler),
    ] + sdk_api.handlers(BaseHandler, sdk_stream))
    app.trading_enabled = _TRADING_ENABLED
    app.stopping = False
    app.market_streams = set()
    app.market_tasks = set()
    app.market_cleanup_error = None
    app.sdk = sdk_api.Service(app, globals(), sdk_codec, catalog)
    return app


def _close_http(ContextInfo):
    global _HTTP_LOOP, _HTTP_SERVER, _HTTP_TIMER, _SDK_SERVICE
    if _SDK_SERVICE is not None:
        _SDK_SERVICE.retire_all("bridge stopped")
        _SDK_SERVICE = None
    timer, server, loop = _HTTP_TIMER, _HTTP_SERVER, _HTTP_LOOP
    _HTTP_TIMER = _HTTP_SERVER = _HTTP_LOOP = None
    if server is not None:
        server.request_callback.stopping = True
    try:
        if server is not None:
            for stream in tuple(server.request_callback.market_streams):
                stream.retire()
    finally:
        try:
            if timer is not None:
                ContextInfo.cancel_schedule_run(timer)
        finally:
            try:
                if server is not None:
                    server.stop()
            finally:
                if loop is not None:
                    if loop.asyncio_loop.is_running():
                        loop.add_callback(loop.stop)
                    else:
                        _finish_http(server, loop)


@contextmanager
def _current_http_loop(loop):
    try:
        previous = asyncio.get_event_loop()
    except RuntimeError:
        previous = None
    asyncio.set_event_loop(loop.asyncio_loop)
    try:
        yield
    finally:
        asyncio.set_event_loop(previous)


def _finish_http(server, loop):
    try:
        if server is not None:
            app = server.request_callback
            with _current_http_loop(loop):
                closing = asyncio.ensure_future(server.close_all_connections())
                # Retired stream lifetimes and closed sockets leave only finite teardown work.
                while not closing.done() or any(not task.done() for task in app.market_tasks):
                    loop.add_callback(loop.stop)
                    loop.start()
                closing.result()
                for task in tuple(app.market_tasks):
                    task.result()
    finally:
        loop.close(all_fds=True)
    if server is not None and server.request_callback.market_cleanup_error is not None:
        raise RuntimeError('QMT market subscription cleanup failed') from server.request_callback.market_cleanup_error


def init(ContextInfo):
    """Register a non-waiting QMT callback; never monopolize its strategy thread."""
    global _HTTP_LOOP, _HTTP_SERVER, _HTTP_TIMER, _SDK_SERVICE
    if _HTTP_LOOP is not None:
        raise RuntimeError('DaQMT bridge is already running')
    account_id = _SDK_CONFIG.get('account', os.environ.get('DAQMT_ACCOUNT', '')).strip()
    if not account_id:
        raise RuntimeError('DAQMT_ACCOUNT is required; account discovery is not a binding')
    _validate_account_context(account_id, ContextInfo)
    required = ('get_trade_detail_data',)
    if _TRADING_ENABLED:
        required += ('passorder', 'cancel', 'can_cancel_order')
    if any(not callable(globals().get(name)) for name in required):
        raise RuntimeError('Run the complete strategy directly inside full QMT')
    if any(not callable(getattr(ContextInfo, name, None)) for name in
           ('schedule_run', 'cancel_schedule_run')):
        raise RuntimeError('Full QMT schedule_run and cancel_schedule_run are required')
    try:
        locale.setlocale(locale.LC_ALL, '')
    except Exception:
        pass
    app = make_app()
    app.ContextInfo = ContextInfo
    app.accountID = account_id
    app.sdk.initialize(ContextInfo)
    _validate_account_context(account_id, ContextInfo)
    _SDK_SERVICE = app.sdk
    port = _SDK_CONFIG.get('_port', int(os.environ.get('DAQMT_PORT', '9001')))
    loop = IOLoop(make_current=False)
    server = None
    _HTTP_LOOP = loop

    def pump(context):
        if _HTTP_LOOP is not loop or loop.asyncio_loop.is_running():
            return
        app.ContextInfo = context
        try:
            with _current_http_loop(loop):
                if app.market_streams:
                    try:
                        _validate_account_context(app.accountID, context)
                    except RuntimeError:
                        for stream in tuple(app.market_streams):
                            stream.retire('account context changed')
                app.sdk.validate_context(context)
                # Ready stop makes one selector turn non-waiting on the QMT thread.
                loop.add_callback(loop.stop)
                loop.start()
        except BaseException:
            _close_http(context)
            raise
        finally:
            if _HTTP_LOOP is not loop and not loop.asyncio_loop.is_closed():
                _finish_http(server, loop)

    try:
        with _current_http_loop(loop):
            server = _HTTP_SERVER = app.listen(port, address=_SDK_CONFIG.get('_address', '127.0.0.1'))
        timer = ContextInfo.schedule_run(
            pump, dt.datetime.now() + dt.timedelta(milliseconds=100),
            -1, dt.timedelta(milliseconds=100))
        if _HTTP_LOOP is not loop:
            ContextInfo.cancel_schedule_run(timer)
            raise RuntimeError('DaQMT bridge stopped during timer registration')
        _HTTP_TIMER = timer
    except BaseException:
        _close_http(ContextInfo)
        raise
    logger.info('DaQMT loopback bridge port=%d trading=%s account_suffix=%s timer=%s',
                port, _TRADING_ENABLED, account_id[-4:], timer)


def handlebar(ContextInfo):
    """Publish lifecycle notifications without generating orders."""
    _sdk_emit("lifecycle.handlebar", ContextInfo)


def stop(ContextInfo):
    """QMT cleanup cancels only this timer and closes only this bridge's resources."""
    _close_http(ContextInfo)
    logger.info('DaQMT bridge stopped')


def _sdk_emit(api, ContextInfo, *args):
    service = _SDK_SERVICE
    if service is not None:
        service.emit(api, *args)


def after_init(ContextInfo):
    _sdk_emit('lifecycle.after_init', ContextInfo)


def account_callback(ContextInfo, data):
    _sdk_emit('callback.account_callback', ContextInfo, data)


def task_callback(ContextInfo, data):
    _sdk_emit('callback.task_callback', ContextInfo, data)


def order_callback(ContextInfo, data):
    _sdk_emit('callback.order_callback', ContextInfo, data)


def deal_callback(ContextInfo, data):
    _sdk_emit('callback.deal_callback', ContextInfo, data)


def position_callback(ContextInfo, data):
    _sdk_emit('callback.position_callback', ContextInfo, data)


def orderError_callback(ContextInfo, data, error_message):
    _sdk_emit('callback.orderError_callback', ContextInfo, data, error_message)


def credit_account_callback(ContextInfo, seq, result):
    _sdk_emit('callback.credit_account_callback', ContextInfo, seq, result)


def credit_opvolume_callback(ContextInfo, accid, seq, ret, result):
    _sdk_emit('callback.credit_opvolume_callback', ContextInfo, accid, seq, ret, result)
