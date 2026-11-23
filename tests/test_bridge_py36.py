"""The bridge runs inside QMT's embedded Python 3.6.8, not this repo's 3.11.

Every other test imports the bridge with the host interpreter, so a 3.8+ construct
passes the whole suite and fails only when the client loads the strategy file.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_BRIDGE = Path(__file__).resolve().parents[1] / "bridge"
_FILES = ("daqmt_server.py", "daqmt_api.py", "daqmt_codec.py", "daqmt_stream.py")


@pytest.mark.parametrize("name", _FILES)
def test_the_bridge_parses_as_python_36(name):
    source = (_BRIDGE / name).read_text(encoding="utf-8")

    ast.parse(source, filename=name, feature_version=(3, 6))
