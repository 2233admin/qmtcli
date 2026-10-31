"""Pinned StockPosition/StockOrder codecs, verified against service record writers."""
import math
import struct

from qmtcli import native_asset as transport


def _text(raw: bytes, offset: int, size: int) -> str:
    return raw[offset:offset + size].split(b'\0', 1)[0].decode('utf-8')


def _identity(raw: bytes, account: str, size: int, symbol: int) -> dict:
    if len(raw) < size:
        raise ValueError(f'native record is shorter than {size} bytes')
    if struct.unpack_from('<i', raw)[0] != 2 or _text(raw, 4, 24) != account:
        raise ValueError('native record does not match requested account/type')
    return {'account_type': 2, 'account_id': account,
            'stock_code': _text(raw, symbol, 64) or _text(raw, 28, 16)}


def decode_position(raw: bytes, account: str) -> dict:
    result = _identity(raw, account, 328, 112)
    fields = ('volume', 'can_use_volume', 'open_price', 'market_value', 'frozen_volume',
              'on_road_volume', 'yesterday_volume')
    result.update(zip(fields, struct.unpack_from('<qqddqqq', raw, 44)))
    if not all(math.isfinite(result[k]) for k in ('open_price', 'market_value')):
        raise ValueError('native position prices must be finite')
    if any(result[k] < 0 for k in ('volume', 'can_use_volume', 'frozen_volume', 'on_road_volume', 'yesterday_volume')):
        raise ValueError('native position quantities must be nonnegative')
    return result


def decode_order(raw: bytes, account: str) -> dict:
    result = _identity(raw, account, 476, 324)
    fields = ('order_id', 'order_time', 'order_type', 'order_volume', 'price_type', 'price',
              'traded_volume', 'traded_price', 'order_status')
    result.update(zip(fields, struct.unpack_from('<iqiiididi', raw, 44)))
    if not all(math.isfinite(result[k]) for k in ('price', 'traded_price')):
        raise ValueError('native order prices must be finite')
    if result['order_volume'] < 0 or result['traded_volume'] < 0:
        raise ValueError('native order quantities must be nonnegative')
    result.update(order_sysid=_text(raw, 92, 24), status_msg=_text(raw, 116, 24),
                  strategy_name=_text(raw, 140, 24),
                  order_remark=_text(raw, 196, 128) or _text(raw, 164, 24))
    return result


def query_native_records(path: str, account: str, account_type: str = 'STOCK',
                         timeout: float = 5, operation: str = 'snapshot') -> dict:
    return transport._query_native(path, account, account_type, timeout, operation=operation)
