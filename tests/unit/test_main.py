import asyncio

import pytest

import milai.main as main_module


# tmp_path and capsys are built-in pytest fixtures:
# * tmp_path gives the test a unique temporary directory as a pathlib.Path
# * capsys captures writes to stdout/stderr during the test
def test_missing_config_path_exits_with_clear_error(tmp_path, capsys) -> None:
    missing = tmp_path / "missing.yaml"

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(main_module.run(["--config", str(missing)]))

    assert exc_info.value.code == 2
    assert f"config file does not exist: {missing}" in capsys.readouterr().err


def test_missing_default_config_uses_defaults(monkeypatch, tmp_path) -> None:
    class DummyMediator:
        pass

    class DummyStateMachine:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def run(self) -> None:
            pass

    monkeypatch.setattr(
        main_module, "DEFAULT_CONFIG_PATH", tmp_path / "missing-config.yaml"
    )
    monkeypatch.setattr(main_module, "TuiMediator", DummyMediator)
    monkeypatch.setattr(main_module, "StateMachine", DummyStateMachine)
    monkeypatch.setattr(
        main_module,
        "load_config",
        lambda path: pytest.fail(f"unexpected config load from {path}"),
    )

    asyncio.run(main_module.run([]))
