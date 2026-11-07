from __future__ import annotations

import pytest

from qmtcli.cli import main


def test_help_documents_escape_hatches(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["data-call", "--help"])
    assert exc.value.code == 0
    assert "public xtquant.xtdata method" in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc:
        main(["trade-call", "--help"])
    assert exc.value.code == 0
    assert "public XtQuantTrader method" in capsys.readouterr().out
