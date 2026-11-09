"""Request-owned SDK/native sessions, with callback-only invalidation/publication."""

from __future__ import annotations

import threading
from typing import Any, Callable

from qmtcli.gateway import QMTConnection, QMTGateway


class AccountSession:
    """Reuse transport state, never account query results. Requests have one owner."""

    def __init__(self, factory: Callable, emit: Callable[[dict], None]):
        self._factory = factory
        self._emit = emit
        self._gateway: QMTGateway | None = None
        self._key: tuple | None = None
        self._lock = threading.RLock()
        self._invalid = threading.Event()
        self._generation = 0
        self._sequence = 0
        self._streaming = False
        self._native = None
        self._native_key = None

    @property
    def native_generation(self) -> int:
        return self._native.generation if self._native is not None else 0

    def native_query(self, connection: QMTConnection, operation: str, timeout: float) -> dict:
        from qmtcli.native_session import NativeSession

        key = (connection.path, connection.account_id, connection.account_type)
        if self._native is None or self._native_key != key:
            if self._native is not None:
                self._native.close()
            self._native = NativeSession(*key)
            self._native_key = key
        return self._native.query(operation, timeout)

    def get(self, connection: QMTConnection, subscribe: bool = True) -> QMTGateway:
        key = (connection.path, connection.account_id, connection.account_type, subscribe)
        if self._gateway is not None and self._key == key and not self._invalid.is_set():
            return self._gateway
        streaming = self._streaming and self._key == key
        self.close()
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._sequence = 0
            self._key = key
            self._streaming = streaming
            self._invalid.clear()
            gateway = self._factory(connection)
            self._gateway = gateway
            gateway.on_event = lambda kind, data: self._on_event(generation, key, kind, data)
        try:
            gateway.connect(subscribe=subscribe)
            if self._invalid.is_set():
                raise RuntimeError("QMT disconnected while connecting")
            if streaming:
                self._on_event(generation, key, "resync_required", None)
        except Exception:
            self.close()
            raise
        return gateway

    def _on_event(self, generation: int, key: tuple, kind: str, data: Any) -> None:
        with self._lock:
            if generation != self._generation or self._gateway is None:
                return
            account = data.get("account_id") if isinstance(data, dict) else getattr(data, "account_id", None)
            if account is not None and account != key[1]:
                return
            self._sequence += 1
            if kind == "disconnected":
                self._invalid.set()
            if self._streaming:
                self._emit({
                    "event": "account_update", "type": kind, "data": data,
                    "account": key[1], "account_type": key[2],
                    "generation": generation, "sequence": self._sequence,
                })

    def subscribe(self, connection: QMTConnection) -> dict:
        self.get(connection)
        with self._lock:
            self._streaming = True
            return {"subscribed": True, **self.cursor()}

    def unsubscribe(self) -> dict:
        with self._lock:
            self._streaming = False
            return {"subscribed": False, **self.cursor()}

    def cursor(self) -> dict:
        with self._lock:
            return {"generation": self._generation, "sequence": self._sequence,
                    "connected": self._gateway is not None and not self._invalid.is_set()}

    def invalidate(self) -> None:
        # stop() waits for SDK callback executors; never call it from a callback.
        self._invalid.set()

    def close(self) -> None:
        with self._lock:
            gateway, self._gateway = self._gateway, None
            self._key = None
            self._streaming = False
            self._generation += 1
            native, self._native = self._native, None
            self._native_key = None
        try:
            if native is not None:
                native.close()
        finally:
            if gateway is not None:
                gateway.close()
