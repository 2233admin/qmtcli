"""The bridge result codec must survive one unreadable native field.

A Full-QMT native object exposes every ``m_`` field, and one getter can raise
while the rest stay readable. Losing the whole result would turn a partial
read into an empty account, so the codec marks the bad field instead.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CODEC = Path(__file__).resolve().parents[1] / "bridge" / "daqmt_codec.py"


@pytest.fixture(scope="module")
def codec():
    spec = importlib.util.spec_from_file_location("daqmt_codec_under_test", _CODEC)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OneBadGetter:
    def __dir__(self):
        return ["m_readable", "m_broken"]

    @property
    def m_readable(self):
        return 1.5

    @property
    def m_broken(self):
        raise RuntimeError("native getter failed")


class OneUnsupportedValue:
    def __dir__(self):
        return ["m_readable", "m_weird"]

    @property
    def m_readable(self):
        return 2

    @property
    def m_weird(self):
        return object()


def test_readable_fields_survive_an_unreadable_one(codec):
    result = codec.encode(OneBadGetter())

    assert result["$type"] == "sdk-object"
    assert result["fields"]["m_readable"] == 1.5
    assert result["fields"]["m_broken"] == {"$type": "unreadable", "class": "RuntimeError"}


def test_unsupported_field_value_is_marked_not_dropped(codec):
    result = codec.encode(OneUnsupportedValue())

    assert result["fields"]["m_readable"] == 2
    assert result["fields"]["m_weird"] == {"$type": "unsupported", "class": "object"}


def test_a_failing_field_does_not_fail_the_whole_list(codec):
    result = codec.encode([OneBadGetter()])

    assert result[0]["fields"]["m_readable"] == 1.5


def test_an_object_without_native_fields_still_fails(codec):
    class NoNativeFields:
        pass

    with pytest.raises(TypeError, match="unsupported SDK result type"):
        codec.encode(NoNativeFields())
