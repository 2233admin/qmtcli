"""Read-only market data from the strategy bridge running inside full QMT.

This talks to ``bridge/daqmt_server.py`` over loopback HTTP. It does not use
``xtquant``: the bridge reaches the native client functions directly, so this
path works where ``xtquant`` cannot connect to full QMT.

    uv run qmtcli market sectors
    uv run qmtcli market stocks --sector 沪深A股
    uv run qmtcli market instrument 600000.SH

Every command reads ``connection.json`` for the endpoint and the bridge secret,
sends ``X-Bridge-Secret``, and never prints the secret. Account-bound queries
stay out of this module: they need the client's trading login, and the bridge
refuses them while it is absent (``bridge/daqmt_api.py:199-206``).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# The API ids this module calls, exactly as they appear in bridge/catalog.json.
# Parameter names are part of the contract: the bridge rejects anything else with
# `unknown or injected parameter` (daqmt_api.py:135-181), so `sectorname` is
# lowercase and `marketCode` is camel case, matching the installed wrappers.
API_SECTORS = "global.get_sector_list"
API_SECTOR_STOCKS = "context.get_stock_list_in_sector"
API_INSTRUMENT_DETAIL = "context.get_instrument_detail"

DEFAULT_TIMEOUT = 5.0


class BridgeError(RuntimeError):
    """The bridge was unreachable or refused the call."""


def connection_path(host_dir: str | None = None) -> Path:
    host = (
        Path(host_dir)
        if host_dir
        else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "QmtCli"
    )
    return host / "daqmt" / "connection.json"


def _load_connection(host_dir: str | None = None) -> dict[str, Any]:
    path = connection_path(host_dir)
    if not path.is_file():
        raise BridgeError(
            f"bridge connection file absent: {path}. "
            "Run `qmtcli-rs setup --account <资金账号> --port 9001` first."
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BridgeError(f"bridge connection file unreadable: {path}: {exc}") from None
    if not isinstance(config, dict):
        raise BridgeError(f"bridge connection file must be a JSON object: {path}")
    return config


def call(
    api: str,
    params: dict[str, Any] | None = None,
    *,
    host_dir: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call one bridge API and return the decoded ``data`` member.

    ``timeout`` is per attempt in seconds. A refused or failing bridge raises
    ``BridgeError`` rather than returning an empty result, because an empty
    result here means "the market had no such record", not "the call failed".
    """
    endpoint, secret, account = _resolve(_load_connection(host_dir))
    body = json.dumps({"api": api, "params": params or {}}).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint}/api/call",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Bridge-Secret": secret,
            # The bridge binds the call to the account it was started with
            # (daqmt_api.py:199-202); sending it lets a mismatch fail as 403
            # instead of as an opaque native error.
            "X-Bridge-Account": account,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise BridgeError(f"bridge refused {api}: HTTP {exc.code} {detail}") from None
    except urllib.error.URLError as exc:
        raise BridgeError(
            f"bridge unreachable at {endpoint}: {exc.reason}. "
            "Is the strategy running inside the QMT client?"
        ) from None
    except (OSError, ValueError) as exc:
        raise BridgeError(f"bridge call to {api} failed: {exc}") from None

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        error = payload.get("error") if isinstance(payload, dict) else None
        raise BridgeError(f"bridge call to {api} failed: {error or payload}")
    return payload.get("data")


def _resolve(config: dict[str, Any]) -> tuple[str, str, str]:
    """Endpoint, secret and account from a loaded connection file."""
    endpoint = str(config.get("endpoint") or "").rstrip("/")
    secret = str(config.get("secret") or "")
    if not endpoint:
        raise BridgeError("bridge connection file has no endpoint")
    if not secret:
        raise BridgeError("bridge connection file has no secret")
    return endpoint, secret, str(config.get("account") or "")


def get(path: str, *, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> Any:
    """GET one bridge endpoint that is not the generic ``/api/call`` route.

    The account endpoints answer fixed shapes built by the bridge's own
    converters (``_position_to_dict`` and friends in ``daqmt_server.py``). They
    do not go through the generic codec, which is why ``/api/holding`` returns
    holdings where ``sdk-call global.get_trade_detail_data POSITION`` fails.
    """
    endpoint, secret, account = _resolve(_load_connection(host_dir))
    request = urllib.request.Request(
        f"{endpoint}{path}",
        headers={"X-Bridge-Secret": secret, "X-Bridge-Account": account},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise BridgeError(f"bridge refused {path}: HTTP {exc.code} {detail}") from None
    except urllib.error.URLError as exc:
        raise BridgeError(
            f"bridge unreachable at {endpoint}: {exc.reason}. "
            "Is the strategy running inside the QMT client?"
        ) from None
    except (OSError, ValueError) as exc:
        raise BridgeError(f"bridge GET {path} failed: {exc}") from None


def sector_list(
    node: str, *, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT
) -> list[str]:
    """Immediate children of one sector node.

    The native ``get_sector_list(node)`` answers ``[children, stocks]``. Measured on
    this client: ``''`` gives ``[[], ['我的', '沪深板块', ...]]`` (the root carries its
    top-level groups in the second slot) and ``'沪深板块'`` gives
    ``[['沪深京A股', '沪深A股', ...], []]``. So the first non-empty slot is the
    child list, and only the root is asymmetric.
    """
    data = call(API_SECTORS, {"node": node}, host_dir=host_dir, timeout=timeout)
    if not isinstance(data, list) or not all(isinstance(part, list) for part in data):
        raise BridgeError(f"unexpected sector payload: {type(data).__name__}")
    children, stocks = (data + [[]])[:2] if len(data) < 2 else data[:2]
    return [str(name) for name in (children or stocks)]


def sector_stocks(
    sector: str, *, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT
) -> list[str]:
    return call(
        API_SECTOR_STOCKS,
        {"sectorname": sector},
        host_dir=host_dir,
        timeout=timeout,
    )


def instrument_detail(
    symbol: str, *, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Contract detail for one ``CODE.MARKET`` symbol, e.g. ``600000.SH``."""
    return call(
        API_INSTRUMENT_DETAIL,
        {"marketCode": symbol},
        host_dir=host_dir,
        timeout=timeout,
    )


def account_asset(
    *, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Cash and total asset for the bridge's bound account (GET /api/account/asset)."""
    return get("/api/account/asset", host_dir=host_dir, timeout=timeout)


def positions(*, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Holdings keyed by ``CODE.MARKET`` (GET /api/holding)."""
    return get("/api/holding", host_dir=host_dir, timeout=timeout)


def orders(
    *, cancelable_only: bool = False, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Today's orders (GET /api/order/status).

    ``cancelable_only`` asks the bridge to filter through the native
    ``can_cancel_order``; the bridge answers 503 when the client does not expose
    it, which surfaces here as a BridgeError rather than a silently wider list.
    """
    flag = "true" if cancelable_only else "false"
    return get(f"/api/order/status?cancelable_only={flag}", host_dir=host_dir, timeout=timeout)


def trades(*, host_dir: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Today's fills (GET /api/trade/status)."""
    return get("/api/trade/status", host_dir=host_dir, timeout=timeout)


def post(
    path: str,
    body: dict[str, Any],
    *,
    host_dir: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """POST one bridge endpoint that is not the generic ``/api/call`` route."""
    endpoint, secret, account = _resolve(_load_connection(host_dir))
    request = urllib.request.Request(
        f"{endpoint}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Bridge-Secret": secret,
            "X-Bridge-Account": account,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise BridgeError(f"bridge refused {path}: HTTP {exc.code} {detail}") from None
    except urllib.error.URLError as exc:
        raise BridgeError(
            f"bridge unreachable at {endpoint}: {exc.reason}. "
            "Is the strategy running inside the QMT client?"
        ) from None
    except (OSError, ValueError) as exc:
        raise BridgeError(f"bridge POST {path} failed: {exc}") from None


def place_order(
    *,
    side: str,
    stock: str,
    volume: int,
    price: float,
    user_order_id: str | None = None,
    dry_run: bool = False,
    host_dir: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """Submit one limit order (POST /api/order/buy|sell).

    A 202 ``submitted`` means the bridge read the order back from the account's
    order book and found it under ``user_order_id``; the reply carries
    ``order_id`` and ``broker_accepted: true``. A 502 ``unknown`` means
    ``passorder`` returned but no order appeared, so the outcome is unknown and
    the key must not be reused without reconciling ``orders()`` first.

    ``user_order_id`` makes a retry safe within one bridge process: the bridge
    copies it into the order's ``m_strRemark`` and answers 409 when the key is
    reused with different terms. After a strategy restart the reservation is
    gone, so reconcile with ``orders()`` before reusing a key.
    """
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    body: dict[str, Any] = {
        "stock": stock,
        "volume": volume,
        "price": price,
        "prType": 11,
    }
    if user_order_id:
        body["user_order_id"] = user_order_id
    if dry_run:
        body["dry_run"] = True
    return post(f"/api/order/{side}", body, host_dir=host_dir, timeout=timeout)


def cancel_order(
    order_sys_id: str,
    *,
    host_dir: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """Cancel one order by its ``m_strOrderSysID`` (POST /api/order/cancel_by_id)."""
    return post(
        "/api/order/cancel_by_id",
        {"order_sys_id": order_sys_id, "account": "stock"},
        host_dir=host_dir,
        timeout=timeout,
    )
