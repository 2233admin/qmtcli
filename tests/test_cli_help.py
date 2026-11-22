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


def test_market_help_renders_the_host_dir_default(capsys):
    # argparse expands `%` in help text, so a literal %LOCALAPPDATA% default has to
    # be escaped as %% or `--help` dies with ValueError instead of printing usage.
    with pytest.raises(SystemExit) as exc:
        main(["market", "--help"])
    assert exc.value.code == 0
    assert "%LOCALAPPDATA%" in capsys.readouterr().out
