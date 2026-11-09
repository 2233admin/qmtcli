"""Pinned MiniQMT trade replies, with independent account validation."""
from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path

from qmtcli import native_asset as transport

SERVICE_SHA256 = "1443f023b59b71386700236400cd77367587e7afde7c29476272407212d266f0"


def validate_trade_runtime(bin_dir: Path) -> None:
    source = bin_dir / "OrderService_mini.dll"
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != SERVICE_SHA256:
        raise RuntimeError("unsupported native MiniQMT build: OrderService_mini.dll fingerprint mismatch")


def query_native_account(path: str, account: str, account_type: str = "STOCK", timeout: float = 5) -> dict:
    """Read asset and trades in one isolated native session, without SDK/cache fallback."""
    return transport._query_native(path, account, account_type, timeout, operation="asset_trades")


def decode_trade(raw: bytes, account: str) -> dict:
    if len(raw) < 552:
        raise ValueError("native trade response is shorter than 552 bytes")

    def text(offset: int, size: int) -> str:
        return raw[offset:offset + size].split(b"\0", 1)[0].decode("utf-8")

    if struct.unpack_from("<i", raw)[0] != 2 or text(4, 24) != account:
        raise ValueError("native trade response does not match requested account/type")
    traded_time, price, volume, amount, order_id, order_type = struct.unpack_from("<qdidii", raw, 68)
    if not math.isfinite(price) or not math.isfinite(amount) or volume < 0:
        raise ValueError("native trade numbers must be finite with nonnegative volume")
    return {
        "account_type": 2, "account_id": account,
        "stock_code": text(392, 64) or text(28, 16),
        "traded_id": text(312, 80) or text(44, 24),
        "traded_time": traded_time, "traded_price": price, "traded_volume": volume,
        "traded_amount": amount, "order_id": order_id, "order_type": order_type,
        "order_sysid": text(104, 24), "strategy_name": text(128, 24),
        "order_remark": text(184, 128) or text(152, 24),
    }


class TradeReplies:
    """Account-validated list replies; defaults preserve the original trade codec."""

    def __init__(self, account: str, session: int, asset_sequence: int = 2, trade_sequence: int = 3,
                 *, record_kind: int = 30003, record_size: int = 552, decoder=decode_trade):
        self.account, self.session = account, session
        self.record_kind, self.record_size, self.decoder = record_kind, record_size, decoder
        self.asset_sequence, self.trade_sequence = asset_sequence, trade_sequence
        self.asset: dict | None = None
        self.rows: list[dict] = []
        self.fragment = bytearray()

    def feed(self, frame: tuple) -> list[dict] | None:
        seq, kind, action, last, source, body = frame
        if source != self.session:
            raise ValueError("native response belongs to another session")
        if kind == 30001 and seq == self.asset_sequence and action == 1 and last:
            if self.asset is not None:
                raise ValueError("duplicate native account validation reply")
            self.asset = transport.decode_asset(body, self.account)
            return None
        if kind == 20000 and seq == self.asset_sequence:
            raise ValueError("native account validation failed")
        if seq != self.trade_sequence or action != 1 or self.asset is None:
            raise ValueError("native list requires validated account and matching response")
        if kind == 20000:
            return self._finish_empty(body, last)
        if kind == 10009:
            body = self._fragment_body(body, last)
            if body is None:
                return None
        elif kind != self.record_kind or self.fragment:
            raise ValueError("unexpected native list response")
        self.rows.append(self.decoder(body, self.account))
        return self.rows if last else None

    def _finish_empty(self, body: bytes, last: bool) -> list[dict]:
        if (not last or self.rows or self.fragment or len(body) < 8
                or struct.unpack_from("<q", body)[0] != -1):
            raise ValueError("invalid native list error/partial response")
        # In this pinned service, -1 means either no account or no rows.
        # The same request's successful asset lookup rules out no account.
        return []

    def _fragment_body(self, body: bytes, last: bool) -> bytes | None:
        if len(body) < 38:
            raise ValueError("truncated native list fragment")
        flag, original, total, size, offset = struct.unpack_from("<IIQQQ", body)
        if (flag != 1 or original != self.record_kind or total != self.record_size or size == 0
                or offset != len(self.fragment) or offset + size > total or 38 + size > len(body)):
            raise ValueError("invalid native list fragment")
        self.fragment.extend(body[38:38 + size])
        if len(self.fragment) < total:
            if last:
                raise ValueError("premature last native list fragment")
            return None
        body = bytes(self.fragment)
        self.fragment.clear()
        return body
