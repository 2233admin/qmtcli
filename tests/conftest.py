import pytest


@pytest.fixture(autouse=True)
def _isolate_xtdc_token(monkeypatch):
    """Do not let an operator's data-service token activate SDK initialization in offline tests."""
    monkeypatch.delenv("QMTCLI_XTDC_TOKEN", raising=False)
