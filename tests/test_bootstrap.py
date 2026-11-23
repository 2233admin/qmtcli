import hashlib
import json

from qmtcli import bootstrap


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_file(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _layout(tmp_path, monkeypatch):
    source = tmp_path / "bridge" / "daqmt_server.py"
    source.parent.mkdir()
    source.write_text("# bridge", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "BRIDGE_SHA256", _sha("# bridge"))  # matches file content
    for name in bootstrap.PINNED_ASSETS[1:]:
        (source.parent / name).write_text("# " + name, encoding="utf-8")
    root = tmp_path / "qmt"
    (root / "python").mkdir(parents=True)
    return source, root


def _host(tmp_path, assets=None):
    host = tmp_path / "host"
    (host / "daqmt").mkdir(parents=True)
    (host / "daqmt" / "connection.json").write_text(
        json.dumps({"secret": "s3cr3t", "assets": assets or {}}), encoding="utf-8"
    )
    return host


def _steps(result):
    return {step["name"]: step for step in result["steps"]}


def test_report_mode_never_writes_the_strategy_file(tmp_path, monkeypatch):
    source, root = _layout(tmp_path, monkeypatch)

    result = bootstrap.run(
        qmt_root=str(root),
        account="123",
        port=19001,
        host_dir=str(tmp_path / "host"),
        bridge_src=str(source),
    )

    steps = _steps(result)
    assert steps["bridge_source"]["ok"] is True
    assert steps["strategy_file"]["ok"] is False
    assert not (root / "python" / bootstrap.STRATEGY_FILENAME).exists()
    assert result["ok"] is False


def test_apply_copies_the_verified_bridge_file(tmp_path, monkeypatch):
    source, root = _layout(tmp_path, monkeypatch)

    result = bootstrap.run(
        qmt_root=str(root),
        account="123",
        port=19001,
        host_dir=str(tmp_path / "host"),
        bridge_src=str(source),
        apply=True,
    )

    installed = root / "python" / bootstrap.STRATEGY_FILENAME
    assert installed.read_text(encoding="utf-8") == "# bridge"
    assert _steps(result)["strategy_file"]["ok"] is True


def test_a_different_strategy_file_is_a_failure_not_a_silent_overwrite(tmp_path, monkeypatch):
    source, root = _layout(tmp_path, monkeypatch)
    (root / "python" / bootstrap.STRATEGY_FILENAME).write_text("# older bridge", encoding="utf-8")

    result = bootstrap.run(
        qmt_root=str(root),
        account="123",
        port=19001,
        host_dir=str(tmp_path / "host"),
        bridge_src=str(source),
        apply=True,
    )

    step = _steps(result)["strategy_file"]
    assert step["ok"] is False
    assert "DIFFERS" in step["detail"]
    assert (root / "python" / bootstrap.STRATEGY_FILENAME).read_text(
        encoding="utf-8"
    ) == "# older bridge"


def test_missing_release_and_connection_are_reported_with_the_command_that_fixes_them(
    tmp_path, monkeypatch
):
    source, root = _layout(tmp_path, monkeypatch)

    result = bootstrap.run(
        qmt_root=str(root),
        account="123",
        port=19001,
        host_dir=str(tmp_path / "host"),
        bridge_src=str(source),
    )

    steps = _steps(result)
    assert steps["fixed_release"]["ok"] is False
    assert bootstrap.FIXED_RELEASE_SHA256 in steps["fixed_release"]["detail"]
    assert "setup --account 123 --port 19001" in steps["connection"]["detail"]


def test_report_mode_flags_undeployed_assets(tmp_path, monkeypatch):
    source, root = _layout(tmp_path, monkeypatch)

    result = bootstrap.run(
        qmt_root=str(root),
        account="123",
        port=19001,
        host_dir=str(_host(tmp_path)),
        bridge_src=str(source),
    )

    step = _steps(result)["bridge_assets"]
    assert step["ok"] is False
    assert "not deployed" in step["detail"]


def test_apply_deploys_every_pinned_asset_and_retargets_the_digests(tmp_path, monkeypatch):
    source, root = _layout(tmp_path, monkeypatch)
    payload = b"#!/bin/sh\n"
    monkeypatch.setattr(bootstrap, "FIXED_RELEASE_SHA256", hashlib.sha256(payload).hexdigest())
    host = _host(tmp_path, {name: "stale" for name in bootstrap.PINNED_ASSETS})
    exe = bootstrap.release_path(host)
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(payload)

    result = bootstrap.run(
        qmt_root=str(root),
        account="123",
        port=19001,
        host_dir=str(host),
        bridge_src=str(source),
        apply=True,
    )

    steps = _steps(result)
    assert result["ok"] is True
    assert steps["bridge_assets"]["ok"] is True
    assert steps["assets_digests"]["ok"] is True
    assets = json.loads((host / "daqmt" / "connection.json").read_text(encoding="utf-8"))["assets"]
    for name in bootstrap.PINNED_ASSETS:
        assert assets[name] == _sha_file(source.parent / name)


def test_retargeting_assets_leaves_the_secret_alone(tmp_path, monkeypatch):
    source, root = _layout(tmp_path, monkeypatch)
    host = _host(tmp_path)

    bootstrap.run(
        qmt_root=str(root),
        account="123",
        port=19001,
        host_dir=str(host),
        bridge_src=str(source),
        apply=True,
    )

    config = json.loads((host / "daqmt" / "connection.json").read_text(encoding="utf-8"))
    assert config["secret"] == "s3cr3t"
