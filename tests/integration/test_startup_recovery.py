import asyncio

import pytest

import milai.main as main_module
from milai.models.state import PersistedState
from milai.models.user_state import UserProfile, UserState
from milai.state.variants import OnboardingState
from milai.storage.errors import StorageError
from tests.fakes.mediator import ScriptedMediator
from tests.fakes.storage_client import InMemoryStorage


class CorruptStorage:
    def __init__(self) -> None:
        self.deleted = False
        self.saved: PersistedState | None = None

    async def load(self) -> PersistedState | None:
        raise StorageError("state is corrupt", corrupt=True)

    async def save(self, state: PersistedState) -> None:
        self.saved = state

    async def delete(self) -> None:
        self.deleted = True


def test_corrupt_state_can_be_deleted_and_replaced_with_fresh_snapshot() -> None:
    storage = CorruptStorage()
    mediator = ScriptedMediator([True])

    selected = asyncio.run(main_module.prepare_launch_snapshot(storage, mediator))

    assert storage.deleted is True
    assert storage.saved == selected
    assert isinstance(selected.app, OnboardingState)
    assert selected.user == UserState()
    assert mediator.errors == [
        "Saved session could not be loaded. The state file appears corrupt."
    ]


def test_corrupt_state_is_preserved_when_recovery_is_declined() -> None:
    storage = CorruptStorage()
    mediator = ScriptedMediator([False])

    with pytest.raises(StorageError):
        asyncio.run(main_module.prepare_launch_snapshot(storage, mediator))

    assert storage.deleted is False
    assert storage.saved is None


def test_reset_confirmation_deletes_existing_saved_session() -> None:
    storage = InMemoryStorage(
        PersistedState(
            user=UserState(profile=UserProfile(target_language="Spanish")),
            app=OnboardingState(),
        )
    )
    mediator = ScriptedMediator([True])

    did_reset = asyncio.run(main_module.maybe_reset_saved_session(storage, mediator))

    assert did_reset is True
    assert asyncio.run(storage.load()) is None


def test_reset_confirmation_can_be_declined_without_deleting_state() -> None:
    saved = PersistedState(
        user=UserState(profile=UserProfile(target_language="Spanish")),
        app=OnboardingState(),
    )
    storage = InMemoryStorage(saved)
    mediator = ScriptedMediator([False])

    did_reset = asyncio.run(main_module.maybe_reset_saved_session(storage, mediator))

    assert did_reset is False
    assert asyncio.run(storage.load()) == saved
