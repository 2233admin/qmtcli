import io
import json
import sys

import pytest

from qmtcli import cli


@pytest.fixture
def native(monkeypatch):
    import qmtcli.native_session as module
    import qmtcli.native_records as records
    calls, workers = [], []

    def query(path, account, account_type='STOCK', timeout=5, operation='snapshot'):
        calls.append(operation)
        return {'asset': {'cash': len(calls)}, 'positions': [{'stock_code': 'SYNTHETIC'}],
                'orders': [], 'trades': []}

    class Worker:
        generation = 1

        def __init__(self, path, account, account_type):
            self.closed = False
            workers.append(self)

        def query(self, operation, timeout):
            return query(None, None, timeout=timeout, operation=operation)

        def close(self):
            self.closed = True

    monkeypatch.setattr(module, 'NativeSession', Worker)
    monkeypatch.setattr(records, 'query_native_records', query)
    monkeypatch.setattr(cli.QMTGateway, 'connect', lambda *a, **k: pytest.fail('SDK connected'))
    monkeypatch.setattr(cli.QMTGateway, 'init_xtdc', lambda *a: pytest.fail('SDK initialized'))
    monkeypatch.setenv('QMTCLI_XTDC_TOKEN', 'unused-for-native')
    return calls, workers


@pytest.mark.parametrize('command', ['positions', 'orders', 'account-snapshot'])
def test_native_cli_bypasses_sdk(native, capsys, command):
    assert cli.main(['--path', 'C:/QMT', '--account', 'A', command, '--backend', 'native']) == 0
    result = json.loads(capsys.readouterr().out)
    if command == 'account-snapshot':
        assert result['ok'] and result['data']['meta']['backend'] == 'native'
    else:
        assert isinstance(result, list)


def test_native_jsonl_snapshot_reuses_worker_and_reads_fresh(native, monkeypatch, capsys):
    request = {'command': 'account_snapshot', 'backend': 'native', 'account': 'A', 'path': 'C:/QMT'}
    monkeypatch.setattr(sys, 'stdin', io.StringIO('\n'.join(json.dumps({**request, 'id': i}) for i in [1, 2])))
    assert cli.main(['server']) == 0
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r['id'] for r in replies] == [1, 2]
    assert [r['data']['asset']['cash'] for r in replies] == [1, 2]
    assert all(r['data']['meta']['native_generation'] == 1 for r in replies)
    assert len(native[1]) == 1 and native[1][0].closed


def test_native_orders_uses_server_cancelable_filter(native):
    reply = cli._handle_rpc_request({'command': 'orders', 'account': 'A', 'path': 'C:/QMT',
                                     'backend': 'native', 'cancelable_only': True})
    assert reply['ok'] and native[0] == ['asset_cancelable_orders']


@pytest.mark.parametrize('value', [1, 'false', None])
def test_native_orders_rejects_ambiguous_filter(native, value):
    reply = cli._handle_rpc_request({'command': 'orders', 'account': 'A', 'backend': 'native',
                                     'cancelable_only': value})
    assert not reply['ok'] and not native[0]


@pytest.mark.parametrize('value', [True, 0, -1, 61, float('nan'), '5'])
def test_native_snapshot_rejects_invalid_budget_before_opening_worker(native, value):
    reply = cli._handle_rpc_request({'command': 'account_snapshot', 'account': 'A',
                                     'backend': 'native', 'timeout': value})
    assert not reply['ok'] and not native[0] and not native[1]


def test_agent_discovery_exposes_native_account_queries():
    commands = {c['name']: c for c in cli.AGENT_CAPABILITIES['commands']}
    for name in ['positions', 'orders', 'account-snapshot']:
        assert 'backend' in commands[name]['inputs']
    from qmtcli.mcp_server import build_tool_specs
    tools = {t['name']: t for t in build_tool_specs()}
    for name in ['qmt_positions', 'qmt_orders', 'qmt_account_snapshot']:
        assert 'backend' in tools[name]['inputSchema']['properties']
