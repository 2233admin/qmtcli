"""Tests for the pandas/numpy-aware ``_json_default`` used by _print_json/_emit.

Real xtdata calls such as get_market_data_ex/get_financial_data return pandas DataFrames (and
sometimes Series, Timestamps, or numpy scalars) instead of plain dict/list/str values, so these
tests exercise that shape directly instead of only the dataclass/`__dict__` fallback paths.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from qmtcli.cli import _json_default


def _dump(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=_json_default))


def test_dataframe_with_range_index_becomes_plain_records():
    df = pd.DataFrame({"open": [10.0, 11.0], "close": [10.5, 11.5]})

    out = _dump(df)

    assert out == [{"open": 10.0, "close": 10.5}, {"open": 11.0, "close": 11.5}]


def test_dataframe_with_time_index_keeps_time_as_a_column():
    idx = pd.DatetimeIndex(["2024-01-01", "2024-01-02"], name="time")
    df = pd.DataFrame({"close": [10.5, 11.5]}, index=idx)

    out = _dump(df)

    assert out == [
        {"time": "2024-01-01T00:00:00", "close": 10.5},
        {"time": "2024-01-02T00:00:00", "close": 11.5},
    ]


def test_nan_becomes_json_null_not_the_nan_token():
    df = pd.DataFrame({"a": [1.0, float("nan")]})

    raw = json.dumps(df, ensure_ascii=False, default=_json_default)

    assert "NaN" not in raw
    out = json.loads(raw)
    assert out == [{"a": 1.0}, {"a": None}]


def test_nat_becomes_json_null():
    df = pd.DataFrame({"t": [pd.Timestamp("2024-01-01"), pd.NaT]})

    out = _dump(df)

    assert out[0]["t"] == "2024-01-01T00:00:00"
    assert out[1]["t"] is None


def test_pd_na_becomes_json_null():
    df = pd.DataFrame({"a": pd.array([1, None], dtype="Int64")})

    out = _dump(df)

    assert out == [{"a": 1}, {"a": None}]


def test_ndarray_becomes_list():
    out = _dump(np.array([1, 2, 3]))

    assert out == [1, 2, 3]


def test_numpy_int64_becomes_native_int():
    out = _dump({"count": np.int64(7)})

    assert out == {"count": 7}
    assert isinstance(out["count"], int)


def test_series_becomes_dict():
    series = pd.Series({"lastPrice": 10.5, "volume": 100})

    out = _dump(series)

    assert out == {"lastPrice": 10.5, "volume": 100.0}


def test_nested_dict_of_dataframes_like_get_market_data_ex():
    close = pd.DataFrame({"600519.SH": [10.0, 11.0]})
    volume = pd.DataFrame({"600519.SH": [100, 200]})
    payload = {"close": close, "volume": volume}

    out = _dump(payload)

    assert out == {
        "close": [{"600519.SH": 10.0}, {"600519.SH": 11.0}],
        "volume": [{"600519.SH": 100}, {"600519.SH": 200}],
    }


def test_nested_dict_of_symbol_to_dataframe_like_financial_data():
    balance = pd.DataFrame({"m_anTime": [20240101], "TOTAL_ASSETS": [1000.0]})
    payload = {"600519.SH": {"Balance": balance}}

    out = _dump(payload)

    assert out["600519.SH"]["Balance"] == [{"m_anTime": 20240101, "TOTAL_ASSETS": 1000.0}]


def test_xtquant_pyd_object_without_dict_scrapes_public_attributes():
    class FakeAccountInfo:
        __slots__ = ("account_id", "account_type")

        def __init__(self):
            self.account_id = "123456"
            self.account_type = 2

        def some_method(self):  # pragma: no cover - must be skipped by the scraper
            return "x"

    FakeAccountInfo.__module__ = "xtquant.xtpythonclient"

    out = _dump([FakeAccountInfo()])

    assert out == [{"account_id": "123456", "account_type": 2}]
