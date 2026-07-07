"""QMT/XtQuant gateway.

QMT bundles xtquant under its own Python site-packages. This module discovers
that SDK path lazily so normal project Python can still drive QMT.
"""

from __future__ import annotations

import importlib
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


QMT_ROOT_CANDIDATES = (
    Path("D:/DFZQxtqmt_client_real_win64"),
    Path("D:/DFZQxtqmt_client_test_win64"),
    Path("C:/DFZQxtqmt_client_real_win64"),
    Path("C:/DFZQxtqmt_client_test_win64"),
)

QMT_INSTALL_HINT = (
    "QMT SDK not found. Install/open broker QMT, or pass --path to userdata_mini "
    "or the QMT install root. This CLI does not auto-download broker software."
)


@dataclass
class QMTConnection:
    path: str
    account_id: str
    account_type: str = "STOCK"
    session_id: int | None = None


class QMTGateway:
    """Small wrapper around xtquant account queries and orders."""

    def __init__(self, connection: QMTConnection):
        self.connection = connection
        self.trader: Any | None = None
        self.account: Any | None = None
        self.xtconstant: Any | None = None

    @staticmethod
    def discover_installations() -> list[dict[str, str]]:
        installs = []
        for root in QMT_ROOT_CANDIDATES:
            userdata = root / "userdata_mini"
            site_packages = root / "bin.x64" / "Lib" / "site-packages"
            xtquant = site_packages / "xtquant"
            if userdata.exists() or xtquant.exists():
                installs.append(
                    {
                        "root": str(root),
                        "userdata_mini": str(userdata),
                        "site_packages": str(site_packages),
                        "xtquant": str(xtquant),
                    }
                )
        return installs

    @staticmethod
    def resolve_path(path: str | None = None) -> str | None:
        if path:
            candidate = Path(path)
            if candidate.name == "userdata_mini":
                return str(candidate)
            userdata = candidate / "userdata_mini"
            if userdata.exists():
                return str(userdata)
            return str(candidate)

        installs = QMTGateway.discover_installations()
        return installs[0]["userdata_mini"] if installs else None

    @staticmethod
    def add_sdk_path(path: str | None = None) -> str | None:
        resolved = QMTGateway.resolve_path(path)
        candidates: list[Path] = []
        if resolved:
            userdata = Path(resolved)
            root = userdata.parent if userdata.name == "userdata_mini" else userdata
            candidates.append(root / "bin.x64" / "Lib" / "site-packages")
        candidates.extend(Path(i["site_packages"]) for i in QMTGateway.discover_installations())

        for site_packages in candidates:
            if (site_packages / "xtquant").exists():
                value = str(site_packages)
                if value not in sys.path:
                    sys.path.insert(0, value)
                return value
        return None

    @staticmethod
    def is_available(path: str | None = None) -> bool:
        QMTGateway.add_sdk_path(path)
        return importlib.util.find_spec("xtquant") is not None

    @staticmethod
    def sdk_diagnostics(path: str | None = None, account_id: str | None = None) -> dict[str, Any]:
        resolved_path = QMTGateway.resolve_path(path)
        sdk_path = QMTGateway.add_sdk_path(resolved_path)
        installations = QMTGateway.discover_installations()
        modules = {}
        for name in ("xtquant", "xtquant.xttrader", "xtquant.xttype", "xtquant.xtconstant"):
            try:
                module = importlib.import_module(name)
            except ImportError as exc:
                modules[name] = {"ok": False, "error": str(exc)}
            else:
                modules[name] = {"ok": True, "file": getattr(module, "__file__", None)}

        xttrader = importlib.import_module("xtquant.xttrader") if modules["xtquant.xttrader"]["ok"] else None
        xttype = importlib.import_module("xtquant.xttype") if modules["xtquant.xttype"]["ok"] else None
        xtconstant = (
            importlib.import_module("xtquant.xtconstant")
            if modules["xtquant.xtconstant"]["ok"]
            else None
        )
        trader_cls = getattr(xttrader, "XtQuantTrader", None) if xttrader else None
        xtquant_ok = modules["xtquant"]["ok"]
        feature_ok = bool(
            trader_cls
            and xttype
            and hasattr(xttype, "StockAccount")
            and xtconstant
            and hasattr(xtconstant, "STOCK_BUY")
            and hasattr(xtconstant, "STOCK_SELL")
            and hasattr(xtconstant, "FIX_PRICE")
        )

        return {
            "xtquant": xtquant_ok,
            "modules": modules,
            "features": {
                "XtQuantTrader": bool(trader_cls),
                "StockAccount": bool(xttype and hasattr(xttype, "StockAccount")),
                "order_stock": bool(trader_cls and hasattr(trader_cls, "order_stock")),
                "cancel_order_stock": bool(
                    trader_cls and hasattr(trader_cls, "cancel_order_stock")
                ),
                "query_stock_trades": bool(
                    trader_cls and hasattr(trader_cls, "query_stock_trades")
                ),
                "STOCK_BUY": bool(xtconstant and hasattr(xtconstant, "STOCK_BUY")),
                "STOCK_SELL": bool(xtconstant and hasattr(xtconstant, "STOCK_SELL")),
                "FIX_PRICE": bool(xtconstant and hasattr(xtconstant, "FIX_PRICE")),
            },
            "inputs": {
                "path_provided": bool(path),
                "resolved_path": resolved_path,
                "path_exists": bool(resolved_path and Path(resolved_path).exists()),
                "sdk_path": sdk_path,
                "account_provided": bool(account_id),
            },
            "installations": installations,
            "diagnosis": {
                "ok": bool(xtquant_ok and feature_ok and resolved_path and Path(resolved_path).exists()),
                "severity": "ok" if xtquant_ok and feature_ok else "error",
                "message": "QMT SDK is usable" if xtquant_ok and feature_ok else QMT_INSTALL_HINT,
                "expected_roots": [str(path) for path in QMT_ROOT_CANDIDATES],
                "fix_hint": (
                    "No action needed"
                    if xtquant_ok and feature_ok
                    else QMT_INSTALL_HINT
                ),
                "auto_download": False,
            },
            "mode": "trade_enabled",
        }

    def connect(self) -> None:
        resolved_path = self.resolve_path(self.connection.path)
        if not resolved_path:
            raise RuntimeError(QMT_INSTALL_HINT)
        self.connection.path = resolved_path
        self.add_sdk_path(resolved_path)

        try:
            xttrader = importlib.import_module("xtquant.xttrader")
            xttype = importlib.import_module("xtquant.xttype")
            self.xtconstant = importlib.import_module("xtquant.xtconstant")
        except ImportError as exc:
            raise RuntimeError("xtquant is not available; install/open broker QMT first") from exc

        session_id = self.connection.session_id or random.randint(1, 2_147_483_647)
        trader = xttrader.XtQuantTrader(self.connection.path, session_id=session_id)
        trader.start()
        result = trader.connect()
        if result not in (0, None):
            raise RuntimeError(f"QMT connect failed: {result}")

        account = xttype.StockAccount(self.connection.account_id, self.connection.account_type)
        subscribed = trader.subscribe(account)
        if subscribed not in (0, None):
            raise RuntimeError(f"QMT account subscribe failed: {subscribed}")

        self.trader = trader
        self.account = account

    def _require_connected(self) -> tuple[Any, Any]:
        if self.trader is None or self.account is None:
            raise RuntimeError("QMTGateway is not connected")
        return self.trader, self.account

    def query_asset(self) -> Any:
        trader, account = self._require_connected()
        return trader.query_stock_asset(account)

    def query_positions(self) -> Any:
        trader, account = self._require_connected()
        return trader.query_stock_positions(account)

    def query_orders(self) -> Any:
        trader, account = self._require_connected()
        return trader.query_stock_orders(account)

    def query_trades(self) -> Any:
        trader, account = self._require_connected()
        return trader.query_stock_trades(account)

    @staticmethod
    def call_data(method: str, *args: Any, **kwargs: Any) -> Any:
        QMTGateway.add_sdk_path()
        xtdata = importlib.import_module("xtquant.xtdata")
        fn = getattr(xtdata, method, None)
        if fn is None or method.startswith("_"):
            raise ValueError(f"unknown xtdata method: {method}")
        return fn(*args, **kwargs)

    def call_trader(self, method: str, *args: Any, with_account: bool = True, **kwargs: Any) -> Any:
        trader, account = self._require_connected()
        fn = getattr(trader, method, None)
        if fn is None or method.startswith("_"):
            raise ValueError(f"unknown XtQuantTrader method: {method}")
        if with_account:
            return fn(account, *args, **kwargs)
        return fn(*args, **kwargs)

    def cancel_order(self, order_id: int | str) -> Any:
        trader, account = self._require_connected()
        return trader.cancel_order_stock(account, int(order_id))

    def submit_order(self, symbol: str, side: str, volume: int, price: float) -> Any:
        trader, account = self._require_connected()
        if volume <= 0 or volume % 100 != 0:
            raise ValueError("A-share order volume must be a positive multiple of 100")
        if price <= 0:
            raise ValueError("price must be positive")

        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")

        constants = self.xtconstant
        order_type = constants.STOCK_BUY if side == "BUY" else constants.STOCK_SELL
        return trader.order_stock(
            account,
            symbol,
            order_type,
            volume,
            constants.FIX_PRICE,
            price,
            "qmtcli",
            "qmtcli",
        )
