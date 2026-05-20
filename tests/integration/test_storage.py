import asyncio
import json

import pytest


def _snapshot():
    from milai.models.state import PersistedState
    from milai.models.user_state import UserProfile, UserState
    from milai.state.variants import OnboardingState

    return PersistedState(
        user=UserState(
            profile=UserProfile(target_language="Spanish", native_language="English")
        ),
        app=OnboardingState(),
    )


def test_local_storage_creates_parent_directory_and_round_trips_state(tmp_path) -> None:
    from milai.storage.local import LocalStorage

    path = tmp_path / "nested" / "state.json"
    storage = LocalStorage(path)
    snapshot = _snapshot()

    async def run_script() -> None:
        await storage.save(snapshot)
        assert await storage.load() == snapshot

    asyncio.run(run_script())

    assert path.exists()
    assert (
        json.loads(path.read_text())["user"]["profile"]["target_language"] == "Spanish"
    )


def test_local_storage_overwrites_atomically_without_tmp_files(tmp_path) -> None:
    from milai.models.state import PersistedState
    from milai.models.user_state import UserProfile, UserState
    from milai.state.variants import AssessmentState, OnboardingState
    from milai.storage.local import LocalStorage

    path = tmp_path / "state.json"
    storage = LocalStorage(path)

    first = PersistedState(
        user=UserState(profile=UserProfile(target_language="Spanish")),
        app=OnboardingState(),
    )
    second = PersistedState(
        user=UserState(profile=UserProfile(target_language="French")),
        app=AssessmentState(current_idx=1),
    )

    async def run_script() -> None:
        await storage.save(first)
        await storage.save(second)
        assert await storage.load() == second

    asyncio.run(run_script())

    assert json.loads(path.read_text())["app"]["type"] == "assessment"
    assert not list(tmp_path.glob("*.tmp"))


def test_local_storage_reports_corrupt_existing_state(tmp_path) -> None:
    from milai.storage.errors import StorageError
    from milai.storage.local import LocalStorage

    path = tmp_path / "state.json"
    path.write_text(
        '{"user": {"profile": "wrong-shape"}, "app": {"type": "onboarding"}}'
    )
    storage = LocalStorage(path)

    async def run_script() -> None:
        with pytest.raises(StorageError) as exc_info:
            await storage.load()
        assert exc_info.value.corrupt is True

    asyncio.run(run_script())
