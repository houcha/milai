import httpx2
import pytest
from openai import RateLimitError

from milai import cli
from milai.config import Settings


def test_probe_quota_message_is_sanitized_and_not_retried(monkeypatch, capsys):
    calls = []

    async def limited(*args):
        calls.append(True)
        raise RateLimitError(
            "provider-private-detail",
            response=httpx2.Response(
                429, request=httpx2.Request("POST", "https://model.invalid")
            ),
            body=None,
        )

    monkeypatch.setattr("sys.argv", ["milai", "probe"])
    monkeypatch.setattr(cli, "probe", limited)
    monkeypatch.setattr(cli, "Telemetry", lambda: None)
    monkeypatch.setattr(
        Settings, "load", lambda: Settings("https://model.invalid", "mock", "secret")
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    output = capsys.readouterr().err
    assert "quota" in output and "no automatic retry" in output
    assert "provider-private-detail" not in output
    assert len(calls) == 1
