import httpx2
import pytest
from openai import RateLimitError

from milai import cli
from milai.config import Settings
from milai.store import Store
from milai.tutor import TutorReply


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


def test_reset_requires_acknowledgement_and_archives_database(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "learning.db"
    original = Store(path)
    original.close()
    monkeypatch.setenv("MILAI_DATABASE", str(path))
    monkeypatch.setattr("sys.argv", ["milai", "reset"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert path.exists()

    monkeypatch.setattr("sys.argv", ["milai", "reset", "--yes"])
    cli.main()
    output = capsys.readouterr().out
    assert "Archived:" in output and "Created schema 2" in output
    assert list(tmp_path.glob("learning.db.legacy-*.bak"))
    reopened = Store(path)
    reopened.close()


def test_cli_renders_persisted_theory_and_exercise_blocks(capsys):
    cli.print_reply(
        TutorReply(
            text="First the rule, then practice.",
            activities=[
                {
                    "kind": "theory",
                    "title": "Past simple",
                    "explanation": "Regular verbs usually add -ed.",
                    "examples": [{"example": "walked", "explanation": "walk + ed"}],
                    "skills": [{"name": "Regular past formation"}],
                },
                {
                    "kind": "exercise",
                    "title": "Yesterday",
                    "context": "A trip",
                    "task": "Complete: I ___ to the station (walk).",
                    "skills": [{"name": "Regular past formation"}],
                },
            ],
        )
    )
    output = capsys.readouterr().out
    assert "[THEORY] Past simple" in output
    assert "[EXERCISE] Yesterday" in output
    assert "Complete: I ___ to the station" in output
