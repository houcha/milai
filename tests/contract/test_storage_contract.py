import asyncio
import json

import pytest


def _fresh_snapshot():
    from milai.models.state import PersistedState
    from milai.models.user_state import UserState
    from milai.state.variants import OnboardingState

    return PersistedState(user=UserState(), app=OnboardingState())


def test_storage_client_protocol_shape_is_async() -> None:
    import inspect

    from milai.storage.client import StorageClient

    assert getattr(StorageClient, "_is_protocol", False)
    assert inspect.iscoroutinefunction(StorageClient.load)
    assert inspect.iscoroutinefunction(StorageClient.save)
    assert inspect.iscoroutinefunction(StorageClient.delete)


def test_in_memory_storage_load_save_delete_contract() -> None:
    from tests.fakes.storage_client import InMemoryStorage

    snapshot = _fresh_snapshot()
    storage = InMemoryStorage()

    async def run_script() -> None:
        assert await storage.load() is None
        await storage.save(snapshot)
        assert await storage.load() == snapshot
        assert storage.save_count == 1
        await storage.delete()
        assert await storage.load() is None
        await storage.delete()

    asyncio.run(run_script())


def test_local_storage_missing_file_returns_none_and_delete_is_idempotent(
    tmp_path,
) -> None:
    from milai.storage.local import LocalStorage

    storage = LocalStorage(tmp_path / "state.json")

    async def run_script() -> None:
        assert await storage.load() is None
        await storage.delete()
        assert await storage.load() is None

    asyncio.run(run_script())


def test_local_storage_round_trips_snapshot_as_json(tmp_path) -> None:
    from milai.storage.local import LocalStorage

    path = tmp_path / "state.json"
    snapshot = _fresh_snapshot()
    storage = LocalStorage(path)

    async def run_script() -> None:
        await storage.save(snapshot)
        assert await storage.load() == snapshot

    asyncio.run(run_script())

    data = json.loads(path.read_text())
    assert data["app"]["type"] == "onboarding"
    assert set(data) == {"user", "app"}
    assert not list(tmp_path.glob("*.tmp"))


def test_local_storage_corrupt_file_raises_recoverable_storage_error(tmp_path) -> None:
    from milai.storage.errors import StorageError
    from milai.storage.local import LocalStorage

    path = tmp_path / "state.json"
    path.write_text("{not valid json")
    storage = LocalStorage(path)

    async def run_script() -> None:
        with pytest.raises(StorageError) as exc_info:
            await storage.load()
        assert exc_info.value.corrupt is True

    asyncio.run(run_script())
