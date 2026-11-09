import struct

import pytest

from qmtcli.native_records import decode_order, decode_position
from qmtcli.native_trades import TradeReplies


def record(size):
    raw = bytearray(size)
    struct.pack_into('<i', raw, 0, 2)
    raw[4:6] = b'A\0'
    raw[28:35] = b'SHORT.X'
    return raw


def test_position_layout_uses_long_symbol_and_int64_quantities():
    raw = record(328)
    raw[112:121] = b'600000.SH'
    struct.pack_into('<qqddqqqd', raw, 44, 2**33, 200, 12.5, 2500, 5, 7, 100, 11.5)
    result = decode_position(raw, 'A')
    assert result == dict(account_type=2, account_id='A', stock_code='600000.SH',
                          volume=2**33, can_use_volume=200, open_price=12.5,
                          market_value=2500, frozen_volume=5, on_road_volume=7,
                          yesterday_volume=100)


def test_order_layout_preserves_zero_identity_and_server_fields():
    raw = record(476)
    raw[324:333] = b'600000.SH'
    raw[92:96] = b'SYS1'
    raw[116:122] = b'status'
    raw[140:144] = b'stra'
    raw[164:169] = b'short'
    raw[196:202] = '备注'.encode()
    struct.pack_into('<iqiiididi', raw, 44, 0, 93500, 23, 100, 11, 12.5, 50, 12.4, 55)
    result = decode_order(raw, 'A')
    assert result['order_id'] == 0 and result['stock_code'] == '600000.SH'
    assert result['order_remark'] == '备注' and result['order_sysid'] == 'SYS1'
    assert result['order_time'] == 93500 and result['price'] == 12.5
    assert result['order_volume'] == 100 and result['traded_volume'] == 50


@pytest.mark.parametrize('decoder,size,offset', [(decode_position, 328, 60), (decode_order, 476, 68)])
def test_record_validation(decoder, size, offset):
    raw = record(size)
    with pytest.raises(ValueError, match='shorter'):
        decoder(raw[:-1], 'A')
    with pytest.raises(ValueError, match='account'):
        decoder(raw, 'OTHER')
    struct.pack_into('<d', raw, offset, float('nan'))
    with pytest.raises(ValueError, match='finite'):
        decoder(raw, 'A')


def test_list_collector_handles_position_fragments_and_rejects_wrong_record_kind():
    replies = TradeReplies('A', 123, record_kind=30004, record_size=328, decoder=decode_position)
    replies.asset = {'account_id': 'A'}
    raw = record(328)
    fragment = struct.pack('<IIQQQ6x', 1, 30004, 328, 100, 0) + raw[:100]
    assert replies.feed((3, 10009, 1, False, 123, fragment)) is None
    with pytest.raises(ValueError, match='fragment'):
        replies.feed((3, 10009, 1, True, 123,
                      struct.pack('<IIQQQ6x', 1, 30002, 328, 228, 100) + raw[100:]))
    result = replies.feed((3, 10009, 1, True, 123,
                           struct.pack('<IIQQQ6x', 1, 30004, 328, 228, 100) + raw[100:]))
    assert result[0]['account_id'] == 'A'


@pytest.mark.parametrize('empty', [False, True])
def test_full_native_wire_plan_validates_account_then_reads_three_lists(monkeypatch, tmp_path, empty):
    import ctypes
    from qmtcli import native_asset as native
    from qmtcli import native_trades
    from test_native_trades import asset, trade

    (tmp_path / 'down_queue_123').write_bytes(b'qmtcli-native-owner:owner')
    monkeypatch.setattr(native, '_paths', lambda p: (tmp_path, tmp_path))
    monkeypatch.setattr(native, '_validate_runtime', lambda p: None)
    monkeypatch.setattr(native_trades, 'validate_trade_runtime', lambda p: None)
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: object(), raising=False)
    monkeypatch.setattr(native.os, 'add_dll_directory',
                        lambda p: type('Directory', (), {'close': lambda s: None})(), raising=False)
    frames = [(1, 10002, 1, True, 123, struct.pack('<q', 123)),
              (2, 30001, 1, True, 123, asset())]
    for seq, kind, raw in [(3, 30004, record(328)), (4, 30002, record(476)), (5, 30003, trade())]:
        frames.append((seq, 20000 if empty else kind, 1, True, 123,
                       struct.pack('<q', -1) if empty else raw))
    frames = iter(frames)
    sent = []

    class Ring:
        def __init__(self, *a, **k):
            pass

        def receive(self, deadline):
            yield from frames

        def send(self, raw, deadline):
            sent.append(native.decode_frame(raw))

    monkeypatch.setattr(native, '_Ring', Ring)
    connection = native._WorkerConnection({'path': str(tmp_path), 'account': 'A', 'session': 123,
                                          'owner': 'owner', 'timeout': 1})
    try:
        result = connection.query('snapshot', 1)
        assert all(len(result[k]) == (0 if empty else 1) for k in ['positions', 'orders', 'trades'])
        assert [(r[0], r[1]) for r in sent] == [(1, 10001), (2, 20005), (3, 20008), (4, 20006), (5, 20007)]
        assert sent[2][5][:108] == native.encode_account('A', 'STOCK') + bytes(80)
        assert sent[3][5][:37] == native.encode_account('A', 'STOCK') + bytes(9)
    finally:
        connection.close()
