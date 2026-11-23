"""A codec gap must name its layer instead of hiding behind a native failure.

`Service.encode` is where a result the codec cannot represent becomes a wire
error. Without a distinct code the operator sees `native_call_failed` and goes
looking inside QMT, while the defect is in the bridge.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1] / "bridge" / "daqmt_api.py"


@pytest.fixture(scope="module")
def api():
    spec = importlib.util.spec_from_file_location("daqmt_api_under_test", _API)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Codec:
    def __init__(self, result):
        self._result = result

    def encode(self, value):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _service(api, codec):
    return api.Service(app=None, namespace={}, codec=codec, catalog={"apis": []})


def test_a_codec_failure_names_the_offending_type(api):
    service = _service(api, _Codec(TypeError("unsupported SDK result type: DetailData")))

    with pytest.raises(api.ApiError) as caught:
        service.encode(object())

    assert caught.value.code == "result_encoding_failed"
    assert "DetailData" in str(caught.value)


def test_a_codec_result_passes_through(api):
    service = _service(api, _Codec({"$type": "sdk-object"}))

    assert service.encode(object()) == {"$type": "sdk-object"}
